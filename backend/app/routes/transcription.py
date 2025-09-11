from concurrent.futures import ThreadPoolExecutor
from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    UploadFile,
    File,
    Form,
)
from uuid import uuid4
import logging
import os
import asyncio
import shutil
from typing import Optional
from dotenv import load_dotenv

from app.models.transcription import (
    Transcript,
    TranscriptionRequest,
    TranscriptionResponse,
    TranscriptSegment,
)
from app.services.transcription import (
    process_video_from_url,
    process_video_from_file,
    cleanup_file,
    cleanup_frames_directory,
)
from app.services.search import search_service
from app.services.visual_processing import visual_processing_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

load_dotenv()

transcription_router = APIRouter()

# Thread pool for CPU-bound operations
executor = ThreadPoolExecutor(max_workers=4)

TEMP_DIR = os.getenv("TMPDIR", "/tmp")
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB limit


@transcription_router.post("/video-url", response_model=TranscriptionResponse)
async def transcribe_video_url(
    request: TranscriptionRequest, background_tasks: BackgroundTasks
):
    """
    Transcribe a video using Whisper.

    1. Downloads the video
    2. Extracts the audio
    3. Transcribes the audio
    4. Returns the transcription and audio URL
    """
    logger.info(f"Received request: {request}")

    id = str(uuid4())
    os.makedirs(TEMP_DIR, exist_ok=True)
    video_path = os.path.join(TEMP_DIR, f"{id}.mp4")
    audio_path = os.path.join(TEMP_DIR, f"{id}.mp3")

    try:
        logger.info(f"Processing video from URL: {request.video_url}")

        result = await asyncio.get_event_loop().run_in_executor(
            executor,
            process_video_from_url,
            str(request.video_url),
            video_path,
            audio_path,
            request.model or "small",
            request.language,
        )

        transcript_text = result["text"]
        segments = [
            TranscriptSegment(
                id=f"{id}_{i}", start=seg["start"], end=seg["end"], text=seg["text"]
            )
            for i, seg in enumerate(result["segments"])
        ]

        # Index text transcript
        search_service.index_transcript(
            Transcript(id=id, text=transcript_text, segments=segments)
        )

        # Process visual information
        try:
            logger.info(f"Starting visual processing for transcript {id}")

            # Extract frames for each segment
            frames_by_segment = await asyncio.get_event_loop().run_in_executor(
                executor,
                visual_processing_service.extract_frames_for_segments,
                video_path,
                segments,
                0.5,  # Extract 1 frame every 2 seconds
            )

            # Generate embeddings for all frames
            all_frame_paths = []
            frame_segment_mapping = {}

            for segment_id, frames in frames_by_segment.items():
                for frame in frames:
                    all_frame_paths.append(frame["path"])
                    frame_segment_mapping[frame["path"]] = (
                        segment_id,
                        frame["timestamp"],
                    )

            if all_frame_paths:
                embeddings = await asyncio.get_event_loop().run_in_executor(
                    executor,
                    visual_processing_service.generate_frame_embeddings,
                    all_frame_paths,
                )

                # Prepare frame data with embeddings
                frame_data_with_embeddings = {}
                for i, frame_path in enumerate(all_frame_paths):
                    segment_id, timestamp = frame_segment_mapping[frame_path]
                    if segment_id not in frame_data_with_embeddings:
                        frame_data_with_embeddings[segment_id] = []
                    frame_data_with_embeddings[segment_id].append(
                        {
                            "timestamp": timestamp,
                            "path": frame_path,
                            "embedding": embeddings[i],
                        }
                    )

                # Index visual embeddings
                search_service.index_visual_embeddings(id, frame_data_with_embeddings)
                logger.info(f"Visual processing completed for transcript {id}")

        except Exception as e:
            logger.error(f"Error during visual processing: {e}")
            # Continue even if visual processing fails

        # Clean up the video file after visual processing
        if os.path.exists(video_path):
            os.remove(video_path)
            logger.info(f"Deleted video file: {video_path}")

        # Add a background task to clean up the audio file after a delay of 1 hour
        background_tasks.add_task(cleanup_file, audio_path)

        # Add a background task to clean up frames directory after 2 hours
        background_tasks.add_task(cleanup_frames_directory, id)

        response = TranscriptionResponse(
            id=id,
            audio_url=f"/media/audio/{id}.mp3",
            language=result["language"],
            text=transcript_text,
            segments=segments,
        )

        return response
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@transcription_router.post("/video-file", response_model=TranscriptionResponse)
async def transcribe_video_file(
    video_file: UploadFile = File(...),
    model: Optional[str] = Form("small"),
    language: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Transcribe an uploaded video file using Whisper.
    """
    logger.info(f"Received file upload: {video_file.filename}")

    id = str(uuid4())
    os.makedirs(TEMP_DIR, exist_ok=True)

    # Save uploaded file with original extension
    file_extension = os.path.splitext(video_file.filename or "video.mp4")[1]
    video_path = os.path.join(TEMP_DIR, f"{id}{file_extension}")
    audio_path = os.path.join(TEMP_DIR, f"{id}.mp3")

    try:
        # Validate file type
        allowed_types = [
            "video/mp4",
            "video/avi",
            "video/mov",
            "video/quicktime",
            "video/x-msvideo",
            "video/mkv",
            "video/webm",
        ]
        if video_file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {video_file.content_type}. Supported types: MP4, AVI, MOV, MKV, WebM",
            )

        # Check file size
        video_file.file.seek(0, 2)  # Seek to end of file
        file_size = video_file.file.tell()
        video_file.file.seek(0)  # Reset to beginning

        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE / (1024 * 1024):.0f} MB. Your file is {file_size / (1024 * 1024):.1f} MB.",
            )

        # Save uploaded file temporarily
        with open(video_path, "wb") as temp_file:
            shutil.copyfileobj(video_file.file, temp_file)

        logger.info(f"Processing uploaded video file: {video_file.filename}")

        # Process the video file (extract audio and transcribe)
        result = await asyncio.get_event_loop().run_in_executor(
            executor,
            process_video_from_file,
            video_path,
            audio_path,
            model or "small",
            language,
        )

        transcript_text = result["text"]
        segments = [
            TranscriptSegment(
                id=f"{id}_{i}", start=seg["start"], end=seg["end"], text=seg["text"]
            )
            for i, seg in enumerate(result["segments"])
        ]

        # Index text transcript
        search_service.index_transcript(
            Transcript(id=id, text=transcript_text, segments=segments)
        )

        # Process visual information
        try:
            logger.info(f"Starting visual processing for transcript {id}")

            # Extract frames for each segment
            frames_by_segment = await asyncio.get_event_loop().run_in_executor(
                executor,
                visual_processing_service.extract_frames_for_segments,
                video_path,
                segments,
                0.5,  # Extract 1 frame every 2 seconds
            )

            # Generate embeddings for all frames
            all_frame_paths = []
            frame_segment_mapping = {}

            for segment_id, frames in frames_by_segment.items():
                for frame in frames:
                    all_frame_paths.append(frame["path"])
                    frame_segment_mapping[frame["path"]] = (
                        segment_id,
                        frame["timestamp"],
                    )

            if all_frame_paths:
                embeddings = await asyncio.get_event_loop().run_in_executor(
                    executor,
                    visual_processing_service.generate_frame_embeddings,
                    all_frame_paths,
                )

                # Prepare frame data with embeddings
                frame_data_with_embeddings = {}
                for i, frame_path in enumerate(all_frame_paths):
                    segment_id, timestamp = frame_segment_mapping[frame_path]
                    if segment_id not in frame_data_with_embeddings:
                        frame_data_with_embeddings[segment_id] = []
                    frame_data_with_embeddings[segment_id].append(
                        {
                            "timestamp": timestamp,
                            "path": frame_path,
                            "embedding": embeddings[i],
                        }
                    )

                # Index visual embeddings
                search_service.index_visual_embeddings(id, frame_data_with_embeddings)
                logger.info(f"Visual processing completed for transcript {id}")

        except Exception as e:
            logger.error(f"Error during visual processing: {e}")
            # Continue even if visual processing fails

        # Clean up the video file after visual processing
        if os.path.exists(video_path):
            os.remove(video_path)
            logger.info(f"Deleted video file: {video_path}")

        # Add a background task to clean up the audio file after a delay
        background_tasks.add_task(cleanup_file, audio_path)

        # Add a background task to clean up frames directory after 2 hours
        background_tasks.add_task(cleanup_frames_directory, id)

        response = TranscriptionResponse(
            id=id,
            audio_url=f"/media/audio/{id}.mp3",
            language=result["language"],
            text=transcript_text,
            segments=segments,
        )

        return response
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error processing uploaded video file: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
