import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException

from app.services.summarization import summarize_by_video_id
from app.models.summarization import SummarizationRequest, SummarizationResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

summarization_router = APIRouter()

executor = ThreadPoolExecutor(max_workers=2)


@summarization_router.post("/transcript", response_model=SummarizationResponse)
async def summarize_transcript(request: SummarizationRequest):
    """
    Summarizes a video transcript using an LLM.
    """
    logger.info(f"Received summarization request for video ID: {request.video_id}")
    if not request.video_id:
        raise HTTPException(status_code=400, detail="Video ID is required")

    logger.info("Starting summarization...")
    try:
        summary = await asyncio.get_event_loop().run_in_executor(
            executor,
            summarize_by_video_id,
            request.video_id,
        )
        if summary is None:
            raise HTTPException(
                status_code=404,
                detail=f"Transcript not found for video ID: {request.video_id}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during summarization: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error during summarization"
        )

    logger.info("Summarization completed successfully")
    return SummarizationResponse(summary=summary)
