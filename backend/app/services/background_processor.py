import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from app.models.transcription import Transcript, TranscriptSegment
from app.models.video import ProcessingStatus, VideoSource
from app.services.search import search_service
from app.services.transcription import (
    download_video,
    extract_audio,
    transcribe_audio,
)
from app.services.video_library import video_library_service
from app.services.visual_processing import visual_processing_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Thread pool for CPU-bound operations
executor = ThreadPoolExecutor(max_workers=2)


class BackgroundProcessor:
    _instance = None
    _queue: asyncio.Queue
    _processing: set[str]
    _running: bool
    _workers: list[asyncio.Task]
    _max_concurrent: int

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._queue = asyncio.Queue()
            cls._instance._processing = set()
            cls._instance._running = False
            cls._instance._workers = []
            cls._instance._max_concurrent = 2
        return cls._instance

    async def start(self):
        """Start background processing workers."""
        if self._running:
            logger.warning("Background processor already running")
            return

        self._running = True
        logger.info(
            f"Starting background processor with {self._max_concurrent} workers"
        )

        # Start worker tasks
        for i in range(self._max_concurrent):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)

    async def stop(self):
        """Stop background processing workers."""
        self._running = False

        # Cancel all worker tasks
        for worker in self._workers:
            worker.cancel()

        # Wait for workers to finish
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

        self._workers = []
        logger.info("Background processor stopped")

    async def enqueue(self, video_id: str):
        """Add a video to the processing queue."""
        await self._queue.put(video_id)
        logger.info(f"Enqueued video {video_id} for processing")

    def get_status(self) -> dict:
        """Get the current processing status."""
        return {
            "queue_length": self._queue.qsize(),
            "processing": list(self._processing),
        }

    async def _worker(self, worker_id: int):
        """Background worker that processes videos from the queue."""
        logger.info(f"Worker {worker_id} started")

        while self._running:
            try:
                # Wait for a video to process (with timeout to check running flag)
                try:
                    video_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                self._processing.add(video_id)
                logger.info(f"Worker {worker_id} processing video {video_id}")

                try:
                    await self._process_video(video_id)
                except Exception as e:
                    logger.error(f"Error processing video {video_id}: {e}")
                    video_library_service.update_video_status(
                        video_id, ProcessingStatus.FAILED, str(e)
                    )
                finally:
                    self._processing.discard(video_id)
                    self._queue.task_done()

            except asyncio.CancelledError:
                logger.info(f"Worker {worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")

        logger.info(f"Worker {worker_id} stopped")

    async def _process_video(self, video_id: str):
        """Process a single video through the full pipeline."""
        video = video_library_service.get_video(video_id)
        if not video:
            logger.error(f"Video not found: {video_id}")
            return

        logger.info(f"Starting processing for video: {video.title} ({video_id})")

        # Update status to processing
        video_library_service.update_video_status(video_id, ProcessingStatus.PROCESSING)

        try:
            # Step 1: Get video file (download if YouTube)
            video_path = video.file_path
            if video.source == VideoSource.YOUTUBE and video.youtube_url:
                logger.info(f"Downloading YouTube video: {video.youtube_url}")
                await asyncio.get_event_loop().run_in_executor(
                    executor, download_video, video.youtube_url, video_path
                )

            if not os.path.exists(video_path):
                raise RuntimeError(f"Video file not found: {video_path}")

            # Step 2: Get video duration and generate thumbnail
            duration = video_library_service.get_video_duration(video_path)
            thumbnail_path = video_library_service.generate_thumbnail(video_id)
            video_library_service.update_video_metadata(
                video_id, duration=duration, thumbnail_path=thumbnail_path
            )

            # Step 3: Extract audio
            audio_path = video_path.rsplit(".", 1)[0] + ".mp3"
            logger.info(f"Extracting audio to: {audio_path}")
            await asyncio.get_event_loop().run_in_executor(
                executor, extract_audio, video_path, audio_path
            )

            # Step 4: Transcribe
            logger.info(f"Transcribing audio with model: {video.whisper_model}")
            result = await asyncio.get_event_loop().run_in_executor(
                executor,
                transcribe_audio,
                audio_path,
                video.whisper_model,
                None,  # Auto-detect language
            )

            # Step 5: Create transcript segments
            transcript_text = result["text"]
            segments = [
                TranscriptSegment(
                    id=f"{video_id}_{i}",
                    start=seg["start"],
                    end=seg["end"],
                    text=seg["text"],
                )
                for i, seg in enumerate(result["segments"])
            ]

            # Step 6: Index transcript in ChromaDB
            logger.info(f"Indexing transcript with {len(segments)} segments")
            search_service.index_transcript(
                Transcript(id=video_id, text=transcript_text, segments=segments)
            )

            # Step 7: Extract frames and generate visual embeddings
            await self._process_visual(video_id, video_path, segments)

            # Step 8: Clean up audio file (keep video file for playback)
            if os.path.exists(audio_path):
                os.remove(audio_path)
                logger.info(f"Cleaned up audio file: {audio_path}")

            # Step 9: Update status to completed
            video_library_service.update_video_status(
                video_id, ProcessingStatus.COMPLETED
            )
            logger.info(f"Video processing completed: {video.title} ({video_id})")

        except Exception as e:
            logger.error(f"Error processing video {video_id}: {e}")
            video_library_service.update_video_status(
                video_id, ProcessingStatus.FAILED, str(e)
            )
            raise

    async def _process_visual(
        self, video_id: str, video_path: str, segments: list[TranscriptSegment]
    ):
        """Extract frames and generate visual embeddings."""
        try:
            logger.info(f"Starting visual processing for video {video_id}")

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
                logger.info(f"Generating embeddings for {len(all_frame_paths)} frames")
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
                search_service.index_visual_embeddings(video_id, frame_data_with_embeddings)
                logger.info(f"Visual processing completed for video {video_id}")
            else:
                logger.warning(f"No frames extracted for video {video_id}")

        except Exception as e:
            logger.error(f"Error during visual processing for {video_id}: {e}")
            # Don't fail the whole processing if visual fails
            # The transcript is still usable


# Singleton instance
background_processor = BackgroundProcessor()
