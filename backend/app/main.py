import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.library import library_router
from app.routes.llms import llm_router
from app.routes.media import media_router
from app.routes.search import search_router
from app.routes.summarization import summarization_router
from app.routes.transcription import executor, transcription_router
from app.services.background_processor import background_processor
from app.services.transcription import get_model, model_cache
from app.services.video_library import video_library_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load default model into memory on startup, start background processor,
    and clean up on shutdown.
    """
    logger.info("Loading default model...")
    try:
        get_model()
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        raise RuntimeError(f"Model loading failed: {e}")

    # Start background processor
    logger.info("Starting background processor...")
    await background_processor.start()

    # Resume any pending or processing videos
    pending_videos = video_library_service.get_pending_videos()
    if pending_videos:
        logger.info(f"Resuming {len(pending_videos)} pending videos...")
        for video in pending_videos:
            await background_processor.enqueue(video.id)

    yield

    # Cleanup
    logger.info("Stopping background processor...")
    await background_processor.stop()

    logger.info("Shutting down thread pool executor...")
    executor.shutdown(wait=True)

    logger.info("Unloading models...")
    model_cache.clear()

    logger.info("Shutting down...")


app = FastAPI(title="Video search and transcription API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transcription_router, prefix="/transcribe")
app.include_router(search_router, prefix="/search")
app.include_router(llm_router, prefix="/llms")
app.include_router(summarization_router, prefix="/summarize")
app.include_router(media_router, prefix="/media")
app.include_router(library_router, prefix="/library")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=9091, reload=True)
