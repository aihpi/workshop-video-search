import logging
import mimetypes
import os
from typing import Generator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse

from app.services.video_library import video_library_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

media_router = APIRouter()

TEMP_DIR = os.getenv("TMPDIR", "/tmp")
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for streaming


def ranged_file_reader(
    file_path: str, start: int, end: int, chunk_size: int = CHUNK_SIZE
) -> Generator[bytes, None, None]:
    """Generator that yields chunks of a file for range requests."""
    with open(file_path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = f.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@media_router.get("/audio/{filename}")
async def get_audio(filename: str):
    """
    Serves an audio file.
    """
    audio_path = os.path.join(TEMP_DIR, filename)

    if not os.path.exists(audio_path):
        logger.warning(f"Audio file not found: {audio_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found"
        )

    logger.info(f"Serving audio file: {audio_path}")
    return FileResponse(audio_path, media_type="audio/mpeg")


@media_router.get("/frames/{video_id}/{filename}")
async def get_frame(video_id: str, filename: str):
    """
    Serves a frame image file.
    """
    # Security check: ensure filename doesn't contain path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename"
        )
    
    # Frames are stored in data/frames/{video_id}/{filename}
    frame_path = os.path.join("data/frames", video_id, filename)

    if not os.path.exists(frame_path):
        logger.warning(f"Frame file not found: {frame_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Frame file not found"
        )

    logger.info(f"Serving frame file: {frame_path}")
    return FileResponse(
        frame_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"}  # Cache for 1 day
    )


@media_router.get("/video/{video_id}")
async def stream_video(video_id: str, request: Request):
    """
    Stream a video file with range request support for seeking.
    """
    video = video_library_service.get_video(video_id)
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
        )

    file_path = video.file_path
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found on disk",
        )

    file_size = os.path.getsize(file_path)

    # Determine content type
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = "video/mp4"

    # Check for range header
    range_header = request.headers.get("range")

    if range_header:
        # Parse range header (e.g., "bytes=0-1023")
        try:
            range_spec = range_header.replace("bytes=", "")
            range_parts = range_spec.split("-")
            start = int(range_parts[0]) if range_parts[0] else 0
            end = int(range_parts[1]) if range_parts[1] else file_size - 1
        except (ValueError, IndexError):
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="Invalid range header",
            )

        # Validate range
        if start >= file_size or end >= file_size or start > end:
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="Range not satisfiable",
            )

        content_length = end - start + 1

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": content_type,
        }

        return StreamingResponse(
            ranged_file_reader(file_path, start, end),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            headers=headers,
            media_type=content_type,
        )
    else:
        # No range header - return full file
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        }

        return FileResponse(
            file_path,
            media_type=content_type,
            headers=headers,
        )


@media_router.get("/thumbnail/{video_id}")
async def get_thumbnail(video_id: str):
    """
    Get the thumbnail for a video.
    """
    video = video_library_service.get_video(video_id)
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video not found"
        )

    if not video.thumbnail_path or not os.path.exists(video.thumbnail_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found"
        )

    return FileResponse(
        video.thumbnail_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )