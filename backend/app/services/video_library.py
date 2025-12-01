import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.models.video import (
    AddVideoResponse,
    ProcessingStatus,
    VideoMetadata,
    VideoSource,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
LIBRARY_FILE = DATA_DIR / "video_library.json"
VIDEOS_DIR = DATA_DIR / "videos"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".webm", ".mov", ".m4v"}


class VideoLibraryService:
    _instance = None
    _videos: dict[str, VideoMetadata] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the video library service."""
        logger.info("Initializing Video Library Service")

        # Create necessary directories
        DATA_DIR.mkdir(exist_ok=True)
        VIDEOS_DIR.mkdir(exist_ok=True)
        THUMBNAILS_DIR.mkdir(exist_ok=True)

        # Load existing library
        self._load_library()

        logger.info(f"Video Library initialized with {len(self._videos)} videos")

    def _load_library(self):
        """Load the video library from JSON file."""
        if LIBRARY_FILE.exists():
            try:
                with open(LIBRARY_FILE, "r") as f:
                    data = json.load(f)
                    for video_id, video_data in data.get("videos", {}).items():
                        # Parse datetime strings
                        if video_data.get("created_at"):
                            video_data["created_at"] = datetime.fromisoformat(
                                video_data["created_at"]
                            )
                        if video_data.get("completed_at"):
                            video_data["completed_at"] = datetime.fromisoformat(
                                video_data["completed_at"]
                            )
                        self._videos[video_id] = VideoMetadata(**video_data)
                logger.info(f"Loaded {len(self._videos)} videos from library")
            except Exception as e:
                logger.error(f"Error loading video library: {e}")
                self._videos = {}
        else:
            self._videos = {}

    def _save_library(self):
        """Save the video library to JSON file."""
        try:
            data = {"videos": {}}
            for video_id, video in self._videos.items():
                video_dict = video.model_dump()
                # Convert datetime to ISO format strings
                if video_dict.get("created_at"):
                    video_dict["created_at"] = video_dict["created_at"].isoformat()
                if video_dict.get("completed_at"):
                    video_dict["completed_at"] = video_dict["completed_at"].isoformat()
                data["videos"][video_id] = video_dict

            with open(LIBRARY_FILE, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved {len(self._videos)} videos to library")
        except Exception as e:
            logger.error(f"Error saving video library: {e}")
            raise

    def get_all_videos(self) -> list[VideoMetadata]:
        """Get all videos in the library."""
        return list(self._videos.values())

    def get_video(self, video_id: str) -> Optional[VideoMetadata]:
        """Get a specific video by ID."""
        return self._videos.get(video_id)

    def get_videos_by_source(self) -> dict[str, list[VideoMetadata]]:
        """Get videos grouped by source (YouTube vs Uploaded)."""
        grouped = {"YouTube": [], "Uploaded": []}
        for video in self._videos.values():
            if video.source == VideoSource.YOUTUBE:
                grouped["YouTube"].append(video)
            else:
                grouped["Uploaded"].append(video)
        return grouped

    def get_pending_videos(self) -> list[VideoMetadata]:
        """Get all videos with pending or processing status."""
        return [
            v
            for v in self._videos.values()
            if v.status in [ProcessingStatus.PENDING, ProcessingStatus.PROCESSING]
        ]

    def add_youtube_video(self, url: str, model: str = "base") -> AddVideoResponse:
        """Add a YouTube video to the library."""
        video_id = str(uuid4())

        # Extract video title from URL using yt-dlp
        title = self._get_youtube_title(url) or f"YouTube Video {video_id[:8]}"

        # Create video metadata
        video = VideoMetadata(
            id=video_id,
            title=title,
            source=VideoSource.YOUTUBE,
            file_path=str(VIDEOS_DIR / f"{video_id}.mp4"),
            youtube_url=str(url),
            whisper_model=model,
            status=ProcessingStatus.PENDING,
            created_at=datetime.now(),
        )

        self._videos[video_id] = video
        self._save_library()

        logger.info(f"Added YouTube video to library: {title} ({video_id})")

        return AddVideoResponse(
            video_id=video_id,
            title=title,
            status=ProcessingStatus.PENDING,
        )

    def add_uploaded_video(
        self, filename: str, file_content: bytes, model: str = "base"
    ) -> AddVideoResponse:
        """Add an uploaded video file to the library."""
        video_id = str(uuid4())

        # Extract title from filename
        title = Path(filename).stem

        # Determine file extension
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_VIDEO_EXTENSIONS:
            ext = ".mp4"  # Default to .mp4

        # Save the video file
        file_path = VIDEOS_DIR / f"{video_id}{ext}"
        with open(file_path, "wb") as f:
            f.write(file_content)

        logger.info(f"Saved uploaded video to: {file_path}")

        # Create video metadata
        video = VideoMetadata(
            id=video_id,
            title=title,
            source=VideoSource.UPLOADED,
            file_path=str(file_path),
            whisper_model=model,
            status=ProcessingStatus.PENDING,
            created_at=datetime.now(),
        )

        self._videos[video_id] = video
        self._save_library()

        logger.info(f"Added uploaded video to library: {title} ({video_id})")

        return AddVideoResponse(
            video_id=video_id,
            title=title,
            status=ProcessingStatus.PENDING,
        )

    def update_video_status(
        self,
        video_id: str,
        status: ProcessingStatus,
        error_message: Optional[str] = None,
    ):
        """Update the processing status of a video."""
        video = self._videos.get(video_id)
        if not video:
            logger.error(f"Video not found: {video_id}")
            return

        video.status = status
        video.error_message = error_message

        if status == ProcessingStatus.COMPLETED:
            video.completed_at = datetime.now()

        self._videos[video_id] = video
        self._save_library()

        logger.info(f"Updated video {video_id} status to {status}")

    def update_video_metadata(
        self,
        video_id: str,
        duration: Optional[float] = None,
        thumbnail_path: Optional[str] = None,
    ):
        """Update video metadata after processing."""
        video = self._videos.get(video_id)
        if not video:
            logger.error(f"Video not found: {video_id}")
            return

        if duration is not None:
            video.duration = duration
        if thumbnail_path is not None:
            video.thumbnail_path = thumbnail_path

        self._videos[video_id] = video
        self._save_library()

    def delete_video(self, video_id: str) -> bool:
        """Delete a video from the library and clean up associated files."""
        video = self._videos.get(video_id)
        if not video:
            logger.error(f"Video not found for deletion: {video_id}")
            return False

        # Delete video file
        if video.file_path and os.path.exists(video.file_path):
            try:
                os.remove(video.file_path)
                logger.info(f"Deleted video file: {video.file_path}")
            except Exception as e:
                logger.error(f"Error deleting video file: {e}")

        # Delete thumbnail
        if video.thumbnail_path and os.path.exists(video.thumbnail_path):
            try:
                os.remove(video.thumbnail_path)
                logger.info(f"Deleted thumbnail: {video.thumbnail_path}")
            except Exception as e:
                logger.error(f"Error deleting thumbnail: {e}")

        # Delete frames directory
        frames_dir = DATA_DIR / "frames" / video_id
        if frames_dir.exists():
            try:
                shutil.rmtree(frames_dir)
                logger.info(f"Deleted frames directory: {frames_dir}")
            except Exception as e:
                logger.error(f"Error deleting frames directory: {e}")

        # Remove from library
        del self._videos[video_id]
        self._save_library()

        logger.info(f"Deleted video from library: {video_id}")
        return True

    def generate_thumbnail(self, video_id: str) -> Optional[str]:
        """Generate a thumbnail for a video."""
        video = self._videos.get(video_id)
        if not video or not video.file_path:
            return None

        if not os.path.exists(video.file_path):
            logger.error(f"Video file not found: {video.file_path}")
            return None

        thumbnail_path = THUMBNAILS_DIR / f"{video_id}.jpg"

        try:
            # Get video duration first
            duration = self.get_video_duration(video.file_path)
            # Capture frame at 10% of the video duration
            timestamp = duration * 0.1 if duration else 5

            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    video.file_path,
                    "-ss",
                    str(timestamp),
                    "-vframes",
                    "1",
                    "-vf",
                    "scale=320:-1",  # Scale to 320px width, maintain aspect ratio
                    "-y",
                    str(thumbnail_path),
                ],
                check=True,
                capture_output=True,
            )

            logger.info(f"Generated thumbnail: {thumbnail_path}")
            return str(thumbnail_path)

        except subprocess.CalledProcessError as e:
            logger.error(f"Error generating thumbnail: {e.stderr.decode()}")
            return None
        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}")
            return None

    def get_video_duration(self, video_path: str) -> Optional[float]:
        """Get the duration of a video in seconds using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            duration = float(result.stdout.strip())
            return duration
        except Exception as e:
            logger.error(f"Error getting video duration: {e}")
            return None

    def _get_youtube_title(self, url: str) -> Optional[str]:
        """Get the title of a YouTube video using yt-dlp."""
        try:
            result = subprocess.run(
                ["yt-dlp", "--get-title", url],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            title = result.stdout.strip()
            # Sanitize title for use as filename
            title = re.sub(r'[<>:"/\\|?*]', "", title)
            return title[:100] if title else None  # Limit title length
        except Exception as e:
            logger.error(f"Error getting YouTube title: {e}")
            return None

    def video_file_exists(self, video_id: str) -> bool:
        """Check if the video file exists on disk."""
        video = self._videos.get(video_id)
        if not video or not video.file_path:
            return False
        return os.path.exists(video.file_path)

    def clear_library(self) -> dict:
        """Clear all videos from the library and clean up all associated files."""
        video_ids = list(self._videos.keys())
        deleted_count = 0
        errors = []

        for video_id in video_ids:
            try:
                video = self._videos.get(video_id)
                if video:
                    # Delete video file
                    if video.file_path and os.path.exists(video.file_path):
                        os.remove(video.file_path)

                    # Delete thumbnail
                    if video.thumbnail_path and os.path.exists(video.thumbnail_path):
                        os.remove(video.thumbnail_path)

                    # Delete frames directory
                    frames_dir = DATA_DIR / "frames" / video_id
                    if frames_dir.exists():
                        shutil.rmtree(frames_dir)

                deleted_count += 1
            except Exception as e:
                logger.error(f"Error cleaning up video {video_id}: {e}")
                errors.append({"video_id": video_id, "error": str(e)})

        # Clear in-memory library
        self._videos = {}
        self._save_library()

        logger.info(f"Cleared library: {deleted_count} videos deleted")
        return {"deleted_count": deleted_count, "errors": errors}


# Singleton instance
video_library_service = VideoLibraryService()
