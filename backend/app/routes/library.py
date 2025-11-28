import logging
import os
import shutil
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.models.video import (
    AddVideosResponse,
    AddVideoResponse,
    AddYouTubeVideoRequest,
    ProcessingStatusResponse,
    TranscriptSegmentResponse,
    VideoDetailResponse,
    VideoLibraryResponse,
    VideoMetadata,
    VideoTranscriptResponse,
)
from app.services.background_processor import background_processor
from app.services.search import search_service
from app.services.video_library import video_library_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

library_router = APIRouter()

ALLOWED_VIDEO_TYPES = [
    "video/mp4",
    "video/avi",
    "video/mov",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/mkv",
    "video/webm",
]


@library_router.get("/videos", response_model=VideoLibraryResponse)
async def get_video_library():
    """Get all videos in the library."""
    videos = video_library_service.get_all_videos()
    processing_count = len(
        [v for v in videos if v.status.value in ["pending", "processing"]]
    )

    return VideoLibraryResponse(
        videos=videos,
        processing_count=processing_count,
        total_count=len(videos),
    )


@library_router.get("/videos/grouped")
async def get_videos_grouped():
    """Get videos grouped by source (YouTube vs Uploaded)."""
    grouped = video_library_service.get_videos_by_source()
    return {
        "groups": [
            {"name": name, "videos": videos} for name, videos in grouped.items()
        ]
    }


@library_router.get("/videos/{video_id}", response_model=VideoDetailResponse)
async def get_video(video_id: str):
    """Get details for a specific video."""
    video = video_library_service.get_video(video_id)
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
        )

    # Get transcript text if available
    transcript_text = None
    segment_count = 0
    try:
        transcript_text = search_service.get_transcript_text_by_video_id(video_id)
        if transcript_text:
            # Count segments by querying the collection
            results = search_service._collection.get(
                where={"video_id": video_id}
            )
            segment_count = len(results.get("documents", []))
    except Exception as e:
        logger.warning(f"Could not get transcript for video {video_id}: {e}")

    return VideoDetailResponse(
        video=video,
        transcript_text=transcript_text,
        segment_count=segment_count,
    )


@library_router.get("/videos/{video_id}/transcript", response_model=VideoTranscriptResponse)
async def get_video_transcript(video_id: str):
    """Get transcript segments for a specific video."""
    video = video_library_service.get_video(video_id)
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
        )

    try:
        results = search_service._collection.get(where={"video_id": video_id})

        if not results or not results["documents"]:
            return VideoTranscriptResponse(
                video_id=video_id, video_title=video.title, segments=[]
            )

        # Build segments from results
        segments = []
        for i, doc in enumerate(results["documents"]):
            metadata = results["metadatas"][i]
            segments.append(
                TranscriptSegmentResponse(
                    segment_id=metadata["id"],
                    start_time=metadata["start_time"],
                    end_time=metadata["end_time"],
                    text=doc,
                )
            )

        # Sort by start time
        segments.sort(key=lambda s: s.start_time)

        return VideoTranscriptResponse(
            video_id=video_id, video_title=video.title, segments=segments
        )

    except Exception as e:
        logger.error(f"Error fetching transcript for video {video_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch transcript",
        )


@library_router.post("/videos/youtube", response_model=AddVideoResponse)
async def add_youtube_video(request: AddYouTubeVideoRequest):
    """Add a YouTube video to the library."""
    logger.info(f"Adding YouTube video: {request.url} with model: {request.model}")

    try:
        response = video_library_service.add_youtube_video(str(request.url), request.model)

        # Enqueue for background processing
        await background_processor.enqueue(response.video_id)

        return response
    except Exception as e:
        logger.error(f"Error adding YouTube video: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add video: {str(e)}",
        )


@library_router.post("/videos/upload", response_model=AddVideosResponse)
async def upload_videos(
    files: list[UploadFile] = File(...),
    model: str = Form(default="base"),
):
    """Upload one or more video files to the library."""
    logger.info(f"Uploading {len(files)} video file(s) with model: {model}")

    added = []
    errors = []

    for file in files:
        try:
            # Validate file type
            if file.content_type not in ALLOWED_VIDEO_TYPES:
                errors.append(
                    {
                        "filename": file.filename,
                        "error": f"Unsupported file type: {file.content_type}",
                    }
                )
                continue

            # Read file content
            content = await file.read()

            # Add to library
            response = video_library_service.add_uploaded_video(
                file.filename or "video.mp4", content, model
            )
            added.append(response)

            # Enqueue for background processing
            await background_processor.enqueue(response.video_id)

            logger.info(f"Added video: {file.filename} ({response.video_id})")

        except Exception as e:
            logger.error(f"Error uploading {file.filename}: {e}")
            errors.append({"filename": file.filename, "error": str(e)})

    return AddVideosResponse(added=added, errors=errors)


@library_router.delete("/videos/{video_id}")
async def delete_video(video_id: str):
    """Delete a video from the library."""
    video = video_library_service.get_video(video_id)
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
        )

    # Delete from ChromaDB
    try:
        # Delete transcript segments
        search_service._collection.delete(where={"video_id": video_id})
        logger.info(f"Deleted transcript segments for video {video_id}")

        # Delete visual embeddings
        search_service._visual_collection.delete(where={"video_id": video_id})
        logger.info(f"Deleted visual embeddings for video {video_id}")
    except Exception as e:
        logger.error(f"Error deleting from ChromaDB: {e}")

    # Delete from library (also cleans up files)
    success = video_library_service.delete_video(video_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete video",
        )

    return {"message": "Video deleted successfully", "video_id": video_id}


@library_router.get("/status", response_model=ProcessingStatusResponse)
async def get_processing_status():
    """Get the current processing queue status."""
    status = background_processor.get_status()
    return ProcessingStatusResponse(
        queue_length=status["queue_length"],
        processing=status["processing"],
    )


@library_router.post("/videos/{video_id}/retry")
async def retry_video(video_id: str):
    """Retry processing a failed video."""
    video = video_library_service.get_video(video_id)
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
        )

    if video.status.value not in ["failed", "pending"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video is {video.status.value}, cannot retry",
        )

    # Reset status and re-enqueue
    from app.models.video import ProcessingStatus

    video_library_service.update_video_status(video_id, ProcessingStatus.PENDING)
    await background_processor.enqueue(video_id)

    return {"message": "Video re-queued for processing", "video_id": video_id}


@library_router.delete("/clear")
async def clear_library():
    """Clear all videos from the library and clean up all associated data."""
    logger.info("Clearing entire video library")

    # Clear ChromaDB collections
    try:
        # Get all unique transcript IDs from the collection
        all_results = search_service._collection.get()
        if all_results and all_results["ids"]:
            search_service._collection.delete(ids=all_results["ids"])
            logger.info(f"Deleted {len(all_results['ids'])} transcript segments from ChromaDB")

        # Clear visual embeddings
        all_visual = search_service._visual_collection.get()
        if all_visual and all_visual["ids"]:
            search_service._visual_collection.delete(ids=all_visual["ids"])
            logger.info(f"Deleted {len(all_visual['ids'])} visual embeddings from ChromaDB")
    except Exception as e:
        logger.error(f"Error clearing ChromaDB: {e}")

    # Clear video library (files and metadata)
    result = video_library_service.clear_library()

    return {
        "message": "Library cleared successfully",
        "deleted_count": result["deleted_count"],
        "errors": result["errors"],
    }
