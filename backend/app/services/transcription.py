import os
import logging
import shutil
import subprocess
import asyncio
import torch
import whisper
from typing import Dict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

model_cache: Dict[str, whisper.Whisper] = {}
DEFAULT_MODEL = "small"


def get_model(model_name: str = DEFAULT_MODEL) -> whisper.Whisper:
    try:
        if model_name not in model_cache:
            logger.info(
                f"Model not found in cache. Loading Whisper {model_name} model."
            )
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading model on {device}")
            model_cache[model_name] = whisper.load_model(model_name, device=device)
        return model_cache[model_name]
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        raise RuntimeError(f"Model loading failed: {e}")


def transcribe_audio(audio_path: str, model_name: str, language: str) -> dict:
    try:
        logger.info(f"Transcribing audio using model {model_name}...")

        # Verify audio file exists and has content
        if not os.path.exists(audio_path):
            raise RuntimeError(f"Audio file does not exist: {audio_path}")

        file_size = os.path.getsize(audio_path)
        if file_size < 1000:
            raise RuntimeError(f"Audio file is too small ({file_size} bytes), cannot transcribe")

        model = get_model(model_name)
        result = model.transcribe(audio_path, language=language)
        logger.info("Transcription completed successfully.")
        return result
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error during transcription: {error_msg}")

        # Provide more helpful error messages
        if "reshape tensor of 0 elements" in error_msg:
            raise RuntimeError("Audio file appears to be empty or invalid. The video may not contain audio.")
        elif "CUDA" in error_msg or "GPU" in error_msg:
            raise RuntimeError(f"GPU error during transcription: {error_msg}")
        else:
            raise RuntimeError(f"Transcription failed: {error_msg}")


def extract_audio(video_path: str, audio_path: str) -> bool:
    """Extracts audio from a video using ffmpeg."""
    try:
        logger.info(f"Extracting audio from {video_path}...")
        subprocess.run(
            [
                "ffmpeg",
                "-i", video_path,
                "-vn",  # Disable video recording
                "-acodec", "libmp3lame",  # Use MP3 codec
                "-ar", "16000",  # Sample rate 16kHz (Whisper's native rate)
                "-ac", "1",  # Mono audio
                "-b:a", "128k",  # Bitrate
                "-y",  # Overwrite output file if it exists
                audio_path
            ],
            check=True,
            capture_output=True,
        )

        # Verify the audio file exists and is not empty
        if not os.path.exists(audio_path):
            raise RuntimeError("Audio file was not created")

        file_size = os.path.getsize(audio_path)
        if file_size < 1000:  # Less than 1KB is likely invalid
            raise RuntimeError(f"Audio file is too small ({file_size} bytes), possibly no audio in video")

        logger.info(f"Audio extracted successfully: {audio_path} ({file_size} bytes)")
        return True

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
        logger.error(f"Error extracting audio: {error_msg}")
        raise RuntimeError(f"Failed to extract audio: {error_msg}")


def download_video(video_url: str, output_path: str) -> None:
    """
    Downloads the video from the given URL using yt-dlp and saves it to the specified path.
    """
    try:
        logger.info(f"Downloading video from URL: {video_url}")
        # Work around YouTube's recent API restrictions by downloading video+audio separately and merging
        # Format: prefer H.264 or VP9 codecs (exclude AV1 which has compatibility issues)
        # Priority: H.264 ≤720p, then VP9 ≤720p, then any non-AV1 ≤720p, then fallback to best
        result = subprocess.run(
            [
                "yt-dlp",
                "-f",
                "bestvideo[height<=720][vcodec^=avc]+bestaudio/bestvideo[height<=720][vcodec^=vp9]+bestaudio/bestvideo[height<=720][vcodec!=av01]+bestaudio/best[height<=720]/best",
                "-o",
                output_path,
                video_url,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info(f"yt-dlp completed. Output path: {output_path}")

        # Check if file exists at expected location
        if not os.path.exists(output_path):
            # yt-dlp might have added an extension, let's check
            output_dir = os.path.dirname(output_path)
            output_basename = os.path.basename(output_path).split(".")[0]

            # List all files in the temp directory that match our basename
            matching_files = [
                f for f in os.listdir(output_dir) if f.startswith(output_basename)
            ]

            if matching_files:
                actual_file = os.path.join(output_dir, matching_files[0])
                logger.info(f"Found downloaded file at: {actual_file}")
                # Rename to our expected location
                os.rename(actual_file, output_path)
                logger.info(f"Renamed to expected location: {output_path}")
            else:
                logger.error(
                    f"No files found matching pattern {output_basename}* in {output_dir}"
                )
                logger.error(f"Directory contents: {os.listdir(output_dir)}")
                raise RuntimeError(f"Video file not created at expected location")

        logger.info(f"Video downloaded successfully: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"yt-dlp command failed with exit code {e.returncode}")
        logger.error(f"yt-dlp stderr: {e.stderr}")
        logger.error(f"yt-dlp stdout: {e.stdout}")
        raise RuntimeError(f"Failed to download video from {video_url}")
    except Exception as e:
        logger.error(f"Unexpected error downloading video: {type(e).__name__}: {e}")
        raise RuntimeError(f"Failed to download video from {video_url}")


def _process_audio_and_transcribe(
    video_path: str, audio_path: str, model_name: str, language: str
) -> Dict:
    """
    Shared logic for audio extraction and transcription.
    """
    is_audio_extracted = extract_audio(video_path, audio_path)

    if not is_audio_extracted:
        logger.error(f"Failed to extract audio from {video_path}")
        raise RuntimeError(f"Failed to extract audio from {video_path}")
    logger.info(f"Audio extracted successfully: {audio_path}")

    transcription_result = transcribe_audio(audio_path, model_name, language)
    logger.info(f"Transcribed video successfully.")

    return transcription_result


def process_video_from_url(
    video_url: str, video_path: str, audio_path: str, model_name: str, language: str
) -> Dict:
    """
    Process a video from URL by downloading, extracting audio, and transcribing.
    """
    try:
        is_video_downloaded = download_video(video_url, video_path)

        if not is_video_downloaded:
            logger.error(f"Failed to download video from {video_url}")
            raise RuntimeError(f"Failed to download video from {video_url}")

        logger.info(f"Video downloaded successfully: {video_path}")

        return _process_audio_and_transcribe(
            video_path, audio_path, model_name, language
        )

    except Exception as e:
        logger.error(f"Error processing video from URL: {e}")
        raise e


def process_video_from_file(
    video_path: str, audio_path: str, model_name: str, language: str
) -> Dict:
    """
    Process a local video file by extracting audio and transcribing.
    """
    try:
        logger.info(f"Processing local video file: {video_path}")

        return _process_audio_and_transcribe(
            video_path, audio_path, model_name, language
        )

    except Exception as e:
        logger.error(f"Error processing local video: {e}")
        raise e


async def cleanup_file(file_path: str, delay: int = 3600) -> None:
    """
    Asynchronously delete a file after a delay.

    Note: When used with FastAPI's BackgroundTasks, this function will be
    executed in a separate task, even though it's async.
    """
    try:
        await asyncio.sleep(delay)
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
        else:
            logger.warning(f"File not found for deletion: {file_path}")
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        # Don't raise the exception in a background task as it would be unhandled
        # Just log it instead


async def cleanup_frames_directory(video_id: str, delay: int = 7200) -> None:
    """
    Asynchronously delete a frames directory after a delay (default = 2 hours).
    """
    try:
        await asyncio.sleep(delay)
        frames_dir = os.path.join("data", "frames", video_id)

        if os.path.exists(frames_dir):
            shutil.rmtree(frames_dir)
            logger.info(f"Deleted frames directory: {frames_dir}")
        else:
            logger.warning(f"Frames directory not found for deletion: {frames_dir}")
    except Exception as e:
        logger.error(f"Error deleting frames directory: {e}")
        # Don't raise the exception in a background task as it would be unhandled
        # Just log it instead
