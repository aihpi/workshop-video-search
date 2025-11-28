import chromadb
import logging
import os
from typing import Optional
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from app.models.transcription import Transcript
from app.models.search import (
    KeywordSearchResponse,
    LLMSearchResponse,
    QueryResult,
    QuestionResponse,
    SearchType,
    SemanticSearchResponse,
    VisualSearchResponse,
)
from app.models.llms import LlmAnswer
from app.services.llms import llm_service
from app.services.visual_processing import visual_processing_service
from app.services.video_library import video_library_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL_NAME",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", "chroma_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "transcript_embeddings")
VISUAL_COLLECTION_NAME = os.getenv("VISUAL_COLLECTION_NAME", "visual_embeddings")


class SearchService:
    _instance = None
    _db = None
    _collection = None
    _visual_collection = None

    def __new__(cls):
        """Singleton pattern to ensure only one instance of EmbeddingService exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._initialize_service()
        return cls._instance

    @classmethod
    def _initialize_service(cls):
        """Initialize the vector database with a custom embedding function."""
        logger.info(f"Initializing Question Answering Service.")
        try:
            cls._db = chromadb.PersistentClient(path=CHROMA_DB_DIR)

            # Create embedding function compatible with Chroma
            embedding_function = SentenceTransformerEmbeddingFunction(
                model_name=EMBEDDING_MODEL_NAME
            )

            cls._collection = cls._db.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},  # Use cosine similarity
                embedding_function=embedding_function,  # Use our model for storing and querying data
            )

            # Visual collection should not use an embedding function since we provide embeddings directly
            cls._visual_collection = cls._db.get_or_create_collection(
                name=VISUAL_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
                embedding_function=None,
            )

            logger.info("Question Answering Service initialized successfully.")

            logger.info(
                f"Model: {EMBEDDING_MODEL_NAME}, Database Path: {CHROMA_DB_DIR}, Collection: {COLLECTION_NAME}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Question Answering Service: {e}")
            raise

    def index_transcript(self, transcript: Transcript):
        """Index a transcript by generating embeddings of the segments and storing them in the vector database."""

        try:
            if not transcript.segments:
                logger.warning("No transcript segments provided for indexing.")
                return

            logger.info(
                f"Indexing {len(transcript.segments)} transcript segments from transcript {transcript.id}."
            )

            documents = [segment.text for segment in transcript.segments]
            metadatas = [
                {
                    "video_id": transcript.id,
                    "start_time": segment.start,
                    "end_time": segment.end,
                    "id": segment.id,
                }
                for segment in transcript.segments
            ]
            ids = [segment.id for segment in transcript.segments]

            self._collection.add(documents=documents, metadatas=metadatas, ids=ids)
            logger.info(
                f"Indexed transcript {transcript.id} with {len(transcript.segments)} segments successfully."
            )
        except Exception as e:
            logger.error(f"Failed to index transcript segments: {e}")
            raise

    def index_visual_embeddings(self, video_id: str, frame_data: dict):
        """Index visual embeddings for frames extracted from a video."""
        try:
            if not frame_data:
                logger.warning("No frame data provided for indexing visual embeddings.")
                return

            all_embeddings = []
            all_metadatas = []
            all_ids = []

            for segment_id, frames in frame_data.items():
                for i, frame in enumerate(frames):
                    # Create a unique ID for each frame using index to avoid duplicates
                    frame_id = f"{segment_id}_frame_{frame['timestamp']:.2f}_{i}"

                    all_embeddings.append(frame["embedding"])
                    all_metadatas.append(
                        {
                            "video_id": video_id,
                            "segment_id": segment_id,
                            "timestamp": frame["timestamp"],
                            "frame_path": frame["path"],
                        }
                    )
                    all_ids.append(frame_id)

            self._visual_collection.add(
                embeddings=all_embeddings,
                metadatas=all_metadatas,
                ids=all_ids,
            )

            logger.info(
                f"Indexed {len(all_embeddings)} visual embeddings for video {video_id}."
            )

        except Exception as e:
            logger.error(f"Failed to index visual embeddings: {e}")
            raise

    def get_transcript_text_by_video_id(self, video_id: str) -> Optional[str]:
        """Retrieve the full text of a transcript by its video ID by reconstructing from segments."""
        try:
            logger.info(f"Retrieving transcript text for video ID: {video_id}")
            where_filter = {"video_id": video_id}

            results = self._collection.get(where=where_filter)
            if not results or not results["documents"]:
                logger.warning(f"No segments found for video ID: {video_id}")
                return None

            documents = results["documents"]
            metadatas = results["metadatas"]

            # Sort segments by start time to ensure proper order
            segment_pairs = list(zip(documents, metadatas))
            segment_pairs.sort(key=lambda x: x[1]["start_time"])

            # Reconstruct full transcript by joining segments
            full_transcript = " ".join([segment[0] for segment in segment_pairs])

            logger.info(
                f"Successfully reconstructed transcript for video ID: {video_id}"
            )
            return full_transcript

        except Exception as e:
            logger.error(f"Failed to retrieve transcript text: {e}")
            raise

    def _build_where_filter(self, video_ids: Optional[list[str]]) -> Optional[dict]:
        """Build ChromaDB where filter for video IDs."""
        if not video_ids:
            return None
        if len(video_ids) == 1:
            return {"video_id": video_ids[0]}
        return {"video_id": {"$in": video_ids}}

    def _get_video_title(self, video_id: str) -> str:
        """Get video title from video library."""
        video = video_library_service.get_video(video_id)
        return video.title if video else video_id

    def query_transcript(
        self,
        question: str,
        video_ids: Optional[list[str]] = None,
        top_k: Optional[int] = 5,
        search_type: Optional[SearchType] = SearchType.KEYWORD,
    ) -> QuestionResponse:
        logger.info(
            f"Querying transcripts with {search_type} search for question: {question}"
        )
        logger.info(f"Video IDs filter: {video_ids if video_ids else 'all videos'}")

        if search_type == SearchType.KEYWORD:
            return self._keyword_search(question, video_ids, top_k)
        elif search_type == SearchType.SEMANTIC:
            return self._semantic_search(question, video_ids, top_k)
        elif search_type == SearchType.LLM:
            return self._llm_search(question, video_ids, top_k)
        elif search_type == SearchType.VISUAL:
            return self._visual_search(question, video_ids, top_k)
        else:
            logger.warning(
                f"Unsupported search type: {search_type}. Defaulting to keyword search."
            )
            return self._keyword_search(question, video_ids, top_k)

    def _keyword_search(
        self, question: str, video_ids: Optional[list[str]], top_k: Optional[int] = None
    ) -> KeywordSearchResponse:
        """Perform a keyword search on transcript segments."""

        try:
            logger.info(f"Performing keyword search for question: {question}")

            # Get all segments for the specified videos
            where_filter = self._build_where_filter(video_ids)

            results = self._collection.get(where=where_filter)

            if not results or not results["documents"]:
                logger.warning(f"No segments found for video IDs: {video_ids}")
                return KeywordSearchResponse(
                    question=question, video_ids=video_ids, results=[]
                )

            documents = results["documents"]
            metadatas = results["metadatas"]

            # Filter documents based on keyword match and keep track of indices
            filtered_results = [
                (i, doc)
                for i, doc in enumerate(documents)
                if question.lower() in doc.lower()
            ]

            if not filtered_results:
                logger.warning(f"No keyword matches found for question: {question}")
                return KeywordSearchResponse(
                    question=question, video_ids=video_ids, results=[]
                )

            if top_k:
                filtered_results = filtered_results[:top_k]

            query_results = [
                QueryResult(
                    segment_id=metadatas[i]["id"],
                    start_time=metadatas[i]["start_time"],
                    end_time=metadatas[i]["end_time"],
                    text=document,
                    video_id=metadatas[i]["video_id"],
                    video_title=self._get_video_title(metadatas[i]["video_id"]),
                    relevance_score=None,
                )
                for i, document in filtered_results
            ]

            logger.info(
                f"Found {len(query_results)} keyword matches for question: {question}"
            )

            response = KeywordSearchResponse(
                question=question, video_ids=video_ids, results=query_results
            )

            return response
        except Exception as e:
            logger.error(f"Failed to perform keyword search: {e}")
            raise

    def _semantic_search(
        self, question: str, video_ids: Optional[list[str]], top_k: Optional[int] = 5
    ) -> SemanticSearchResponse:
        """Perform a semantic search on the vector database using embeddings."""

        try:
            logger.info(f"Performing semantic search for question: {question}")

            # Restrict results to specific videos if video_ids is provided
            where_filter = self._build_where_filter(video_ids)

            results = self._collection.query(
                query_texts=[question], n_results=top_k, where=where_filter
            )
            documents = (
                results["documents"][0] if results and results["documents"] else []
            )

            if not documents:
                logger.warning(f"No semantic matches found for question: {question}")
                return SemanticSearchResponse(
                    question=question, video_ids=video_ids, results=[]
                )

            distances = results["distances"][0]

            metadatas = results["metadatas"][0]

            query_results = [
                QueryResult(
                    segment_id=metadatas[i]["id"],
                    start_time=metadatas[i]["start_time"],
                    end_time=metadatas[i]["end_time"],
                    text=document,
                    video_id=metadatas[i]["video_id"],
                    video_title=self._get_video_title(metadatas[i]["video_id"]),
                    relevance_score=round((1 - distances[i]) * 100, 2),
                )
                for i, document in enumerate(documents)
            ]

            logger.info(
                f"Found {len(query_results)} semantic matches for question: {question}"
            )

            response = SemanticSearchResponse(
                question=question, results=query_results, video_ids=video_ids
            )

            return response
        except Exception as e:
            logger.error(f"Failed to perform semantic search: {e}")
            raise

    def _llm_search(
        self, question: str, video_ids: Optional[list[str]], top_k: Optional[int] = 5
    ) -> LLMSearchResponse:
        """Use an LLM to synthesize an answer from semantic search results."""

        try:
            # First, get semantic search results (for returning in response)
            semantic_search_response: SemanticSearchResponse = self._semantic_search(
                question, video_ids, top_k
            )

            # Second, get all segments for the videos (for LLM context)
            where_filter = self._build_where_filter(video_ids)
            all_segments_result = self._collection.get(where=where_filter)

            if not all_segments_result or not all_segments_result["documents"]:
                logger.warning(f"No transcript found for LLM synthesis: {question}")
                return LLMSearchResponse(
                    question=question,
                    video_ids=video_ids,
                    results=[],
                    summary="No transcript found.",
                    not_addressed=True,
                    model_id="none",
                )

            # Convert all segments to QueryResult format and sort by start time
            all_segments = []
            for i, doc in enumerate(all_segments_result["documents"]):
                metadata = all_segments_result["metadatas"][i]
                all_segments.append(
                    QueryResult(
                        segment_id=metadata["id"],
                        start_time=metadata["start_time"],
                        end_time=metadata["end_time"],
                        text=doc,
                        video_id=metadata["video_id"],
                        video_title=self._get_video_title(metadata["video_id"]),
                        relevance_score=None,
                    )
                )

            # Sort by start time to maintain chronological order
            all_segments.sort(key=lambda x: x.start_time)

            logger.info(f"Generating LLM synthesis for question: {question}")
            logger.info(f"Using {len(all_segments)} segments for full context")

            # Pass all segments to LLM for synthesis
            answer: LlmAnswer = llm_service.generate_answer(question, all_segments)

            answer_response = LLMSearchResponse(
                question=question,
                video_ids=video_ids,
                summary=answer.summary,
                not_addressed=answer.not_addressed,
                model_id=answer.model_id,
                results=semantic_search_response.results,
            )

            return answer_response

        except Exception as e:
            logger.error(f"Error generating LLM response: {e}")
            raise

    def _visual_search(
        self, question: str, video_ids: Optional[list[str]], top_k: Optional[int] = 5
    ) -> VisualSearchResponse:
        """Perform a visual-only search using SigLIP embeddings."""
        try:
            logger.info(f"Performing visual search for question: {question}")
            logger.info(f"Video IDs: {video_ids}")

            # Generate SigLIP2 text embedding for the query
            query_embedding = visual_processing_service.generate_text_embedding(
                question
            )
            logger.info(f"Generated query embedding of length: {len(query_embedding)}")

            # Restrict results to specific videos if video_ids is provided
            where_filter = self._build_where_filter(video_ids)

            results = self._visual_collection.query(
                query_embeddings=[query_embedding],
                n_results=(
                    top_k * 3
                ),  # Fetch more to ensure we get enough unique segments
                where=where_filter,
            )

            logger.info(
                f"Visual collection query returned: {len(results.get('metadatas', [[]])[0])} results"
            )

            if not results or not results["metadatas"][0]:
                logger.warning(
                    f"No visual frame matches found for question: {question}"
                )
                return VisualSearchResponse(
                    question=question, video_ids=video_ids, results=[]
                )

            metadatas = results["metadatas"][0]
            distances = results["distances"][0]

            logger.info(
                f"Found {len(metadatas)} visual frame matches for question: {question}"
            )

            logger.info(
                f"Returning top {top_k} unique visual segments based on frame matches."
            )

            # Store best frame for each segment
            top_k_segments = {}  # segment_id -> (distance, frame_metadata)
            for i, metadata in enumerate(metadatas):
                segment_id = metadata["segment_id"]
                if segment_id not in top_k_segments:
                    top_k_segments[segment_id] = (distances[i], metadata)
                    if len(top_k_segments) >= top_k:
                        break

            segment_results = self._collection.get(
                ids=list(top_k_segments.keys()), where=where_filter
            )

            if not segment_results or not segment_results["documents"]:
                logger.warning(
                    f"No visual segment matches found for question: {question}"
                )
                return VisualSearchResponse(
                    question=question, video_ids=video_ids, results=[]
                )

            segment_documents = (
                segment_results["documents"]
                if segment_results and segment_results["documents"]
                else []
            )

            segment_metadatas = segment_results["metadatas"]

            query_results = []
            for i, document in enumerate(segment_documents):
                segment_id = segment_metadatas[i]["id"]
                distance, frame_metadata = top_k_segments[segment_id]
                video_id = segment_metadatas[i]["video_id"]

                # Convert file system path to URL
                frame_path = frame_metadata.get("frame_path")
                frame_url = None
                if frame_path:
                    # Extract video_id and filename from path like "data/frames/{video_id}/{filename}"
                    path_parts = frame_path.split("/")
                    if (
                        len(path_parts) >= 4
                        and path_parts[0] == "data"
                        and path_parts[1] == "frames"
                    ):
                        vid_id = path_parts[2]
                        filename = path_parts[3]
                        frame_url = f"/media/frames/{vid_id}/{filename}"

                query_results.append(
                    QueryResult(
                        segment_id=segment_id,
                        start_time=segment_metadatas[i]["start_time"],
                        end_time=segment_metadatas[i]["end_time"],
                        text=document,
                        video_id=video_id,
                        video_title=self._get_video_title(video_id),
                        relevance_score=round((1 - distance) * 100, 2),
                        frame_timestamp=frame_metadata.get("timestamp"),
                        frame_path=frame_url,
                    )
                )

            # Sort by relevance score in descending order
            query_results = sorted(
                query_results, key=lambda x: x.relevance_score, reverse=True
            )

            logger.info(
                f"Found {len(query_results)} visual segment matches for question: {question}"
            )

            response = VisualSearchResponse(
                question=question,
                results=query_results,
                video_ids=video_ids,
            )

            return response
        except Exception as e:
            logger.error(f"Failed to perform visual search: {e}")
            raise

search_service = SearchService()
