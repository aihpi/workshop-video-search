import logging
import os
import re
import torch
from typing import List, Optional
from openai import OpenAI
from dotenv import load_dotenv

from app.models.llms import LlmAnswer, LlmInfo
from app.models.search import QueryResult

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class LLMService:
    """
    LLM service that works with OpenAI-compatible APIs (Ollama, vLLM, etc.)
    """

    _instance = None
    _client = None
    _backend = None
    _base_url = None
    _api_key = None
    _model_id = None
    _device = None
    _has_gpu = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the LLM service based on environment configuration."""

        # Check for CUDA (NVIDIA) or MPS (Apple Silicon)
        if torch.cuda.is_available():
            self._device = "cuda"
            self._has_gpu = True
            logger.info("Using CUDA GPU for inference")
        elif torch.backends.mps.is_available() and torch.backends.mps.is_built():
            self._device = "mps"
            self._has_gpu = True
            logger.info("Using Apple Silicon GPU (MPS) for inference")
        else:
            self._device = "cpu"
            self._has_gpu = False
            logger.info("Using CPU for inference")

        # Select backend (Ollama/vLLM)
        self._backend = os.getenv("LLM_BACKEND", "ollama").lower()

        if self._backend == "ollama":
            self._base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11437/v1")
            self._api_key = "ollama"  # Ollama doesn't require API key
            self._model_id = os.getenv("LLM_MODEL", "qwen3:8b")
            logger.info(
                f"Using Ollama backend at {self._base_url} with model {self._model_id}"
            )
        elif self._backend == "vllm":
            self._base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
            self._api_key = os.getenv("VLLM_API_KEY", "vllm")
            self._model_id = os.getenv("LLM_MODEL", "qwen3:8b")
            logger.info(
                f"Using vLLM backend at {self._base_url} with model {self._model_id}"
            )
        else:
            raise ValueError(f"Unsupported LLM backend: {self._backend}")

        # Initialize OpenAI client
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
        )

        logger.info(
            f"Initialized {self._backend} LLM service with model: {self._model_id}"
        )

    def generate_answer(
        self, question: str, segments: List[QueryResult], max_new_tokens: int = 512
    ) -> LlmAnswer:
        """Generate a structured answer using the LLM."""
        try:
            prompt = self._create_prompt(question, segments)

            # Use chat completions API
            response = self._client.chat.completions.create(
                model=self._model_id,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant analyzing video transcripts. You always respond in the same language as the transcript you are analyzing, regardless of the language of the question.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_new_tokens,
                temperature=0.7,
            )

            response_text = response.choices[0].message.content

            answer = self._parse_response(response_text, question)

            return answer

        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return LlmAnswer(
                summary=f"Error generating answer: {str(e)}",
                not_addressed=True,
                model_id=self._model_id,
            )

    def _create_prompt(self, question: str, segments: List[QueryResult]) -> str:
        """Create a structured prompt for the LLM."""
        # Join all segment texts without timestamps for cleaner context
        context = " ".join([segment.text for segment in segments])

        prompt = f"""You are analyzing a video transcript to answer a question.
Based on the transcript below, provide a comprehensive answer.

CRITICAL LANGUAGE REQUIREMENT:
- You MUST write your answer in the SAME LANGUAGE as the transcript
- If the transcript is in German, write your answer in German
- If the transcript is in English, write your answer in English
- If the transcript is in any other language, write your answer in that language
- Do NOT translate to a different language
- The user's question might be in a different language, but ALWAYS answer in the transcript's language

Transcript:
{context}

Question: {question}

You MUST format your response EXACTLY as follows:

SUMMARY:
[Write 2-3 sentences summarizing the answer IN THE SAME LANGUAGE AS THE TRANSCRIPT]

COMPLETENESS:
[State one of: "COMPLETE" if the transcript fully answers the question, "PARTIAL" if only some aspects are covered, or "NOT FOUND" if the transcript doesn't contain relevant information]

Remember: 
- Start your response directly with "SUMMARY:" without any preamble
- Write your answer in the SAME LANGUAGE as the transcript above"""

        return prompt

    def _parse_response(self, response: str, question: str) -> LlmAnswer:
        """Parse the LLM response into structured format."""
        summary = ""
        not_addressed = False

        response = response.strip()

        # Clean up any thinking tags or meta-commentary
        if "<think>" in response:
            # Remove everything between <think> and </think>
            response = re.sub(
                r"<think>.*?</think>", "", response, flags=re.DOTALL
            ).strip()

        # Remove any leading/trailing whitespace or empty lines
        response = response.strip()

        # If response contains SUMMARY:, extract from there onwards (ignoring any preceding text)
        summary_start = response.find("SUMMARY:")
        if summary_start != -1:
            response = response[summary_start:]

        logger.info(f"Parsing response: {response[:200]}...")  # Log first 200 chars

        # Extract SUMMARY section
        summary_match = re.search(
            r"SUMMARY:\s*\n?(.*?)(?=COMPLETENESS:|$)",
            response,
            re.DOTALL | re.IGNORECASE,
        )
        if summary_match:
            summary = summary_match.group(1).strip()
            # Remove any bullet points or extra formatting
            summary = " ".join(summary.split())  # Normalize whitespace

        # Extract COMPLETENESS section
        completeness_match = re.search(
            r"COMPLETENESS:\s*\n?(.*?)(?:\n|$)", response, re.DOTALL | re.IGNORECASE
        )
        if completeness_match:
            completeness_str = completeness_match.group(1).strip().upper()
            if "NOT FOUND" in completeness_str or "NOT_FOUND" in completeness_str:
                not_addressed = True
            else:
                not_addressed = False

        # Fallbacks if parsing fails
        if not summary:
            # Try to extract first paragraph as summary
            first_para = response.split("\n\n")[0].strip()
            if first_para and not first_para.startswith(("SUMMARY:", "COMPLETENESS:")):
                summary = first_para
            else:
                summary = f"Analysis of the video transcript regarding: {question}"

        return LlmAnswer(
            summary=summary,
            not_addressed=not_addressed,
            model_id=self._model_id,
        )

    def generate_summary(self, transcript: str, max_new_tokens: int = 512) -> str:
        prompt = f"""You are an AI assistant tasked with summarizing a video transcript.
Here is the transcript:
{transcript}
Please provide a concise summary of the main points in 2-3 sentences."""
        inputs = self._active_tokenizer(
            prompt, return_tensors="pt", truncation=True, max_length=2048
        )
        if (
            self._device == "cuda"
            and "device_map" not in self._models[self._active_model_id]
        ):
            inputs = inputs.to(self._device)
        with torch.no_grad():
            outputs = self._active_model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.7,
                do_sample=True,
                top_p=0.9,
            )
        response = self._active_tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
        )
        return response.strip()

    def get_available_models(self) -> List[LlmInfo]:
        """Get list of available models (just the configured one)."""
        return [
            LlmInfo(
                model_id=self._model_id,
                display_name=self._model_id,
                hf_model_id=os.getenv("LLM_MODEL", "Qwen/Qwen3-8B-Instruct"),
                requires_gpu=True,
                loaded=True,
            )
        ]

    def get_active_model_id(self) -> Optional[str]:
        """Get the currently active model ID."""
        return self._model_id

    def select_model(self, model_id: str) -> bool:
        """Model selection not supported in this simplified version."""
        logger.warning(
            "Model selection not supported. Use LLM_MODEL environment variable."
        )
        return True

    def has_gpu(self) -> bool:
        return self._has_gpu


llm_service = LLMService()
