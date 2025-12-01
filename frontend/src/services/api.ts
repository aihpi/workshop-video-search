import axios from "axios";

import type {
  TranscriptionRequest,
  TranscriptionResponse,
  WhisperModelType,
} from "../types/transcription.types";
import type {
  QuestionRequest,
  QuestionResponse,
  SearchType,
} from "../types/search.types";

import type {
  LlmInfo,
  LlmListResponse,
  LlmSelectResponse,
} from "../types/llms.types";

import type {
  SummarizationRequest,
  SummarizationResponse,
} from "../types/summarization.types";

import type {
  AddVideoResponse,
  AddVideosResponse,
  ProcessingStatusResponse,
  VideoGroupsResponse,
  VideoLibraryResponse,
  VideoTranscriptResponse,
} from "../types/library.types";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:9091";

const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

export const transcribeVideoUrl = async (
  videoUrl: string,
  model?: WhisperModelType,
  language?: string
): Promise<TranscriptionResponse> => {
  // Convert empty string to null for language
  // This ensures FastAPI/Pydantic properly recognizes it as Optional[str]
  const requestBody: TranscriptionRequest = {
    videoUrl,
    model,
    language: language === "" ? null : language,
  };

  try {
    const response = await apiClient.post<TranscriptionResponse>(
      "/transcribe/video-url",
      requestBody
    );
    return response.data;
  } catch (error) {
    console.error("Error during transcription:", error);
    throw error;
  }
};

export const transcribeVideoFile = async (
  videoFile: File,
  model?: WhisperModelType,
  language?: string
): Promise<TranscriptionResponse> => {
  const formData = new FormData();
  formData.append("video_file", videoFile);

  if (model) {
    formData.append("model", model);
  }

  if (language && language !== "") {
    formData.append("language", language);
  }

  try {
    const response = await axios.post<TranscriptionResponse>(
      `${API_URL}/transcribe/video-file`,
      formData,
      {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      }
    );
    return response.data;
  } catch (error) {
    console.error("Error during file transcription:", error);
    throw error;
  }
};

export const queryTranscript = async (
  question: string,
  videoIds?: string[] | null,
  topK: number = 5,
  searchType: SearchType = "keyword"
): Promise<QuestionResponse> => {
  const requestBody: QuestionRequest = {
    question,
    videoIds: videoIds || undefined,
    topK,
    searchType,
  };

  try {
    const response = await apiClient.post<QuestionResponse>(
      "/search/query",
      requestBody
    );
    return response.data;
  } catch (error) {
    console.error("Error during query:", error);
    throw error;
  }
};

export const getCurrentLlmInfo = async (): Promise<LlmInfo | null> => {
  try {
    const response = await apiClient.get("/llms/current");
    return response.data;
  } catch (error) {
    console.error("Error while retrieving current LLM info:", error);
    throw error;
  }
};

export const listLlms = async (): Promise<LlmListResponse> => {
  try {
    const response = await apiClient.get("/llms");
    return response.data;
  } catch (error) {
    console.error("Error while retrieving list of available models", error);
    throw error;
  }
};

export const selectLlm = async (
  modelId: string
): Promise<LlmSelectResponse> => {
  try {
    const response = await apiClient.post("/llms/select", { modelId });
    return response.data;
  } catch (error) {
    console.error(`Error selecting model ${modelId}`, error);
    throw error;
  }
};

export const summarizeTranscript = async (
  videoId: string
): Promise<SummarizationResponse> => {
  const requestBody: SummarizationRequest = {
    videoId,
  };

  try {
    const response = await apiClient.post<SummarizationResponse>(
      "/summarize/transcript",
      requestBody
    );
    return response.data;
  } catch (error) {
    console.error("Error during summarization:", error);
    throw error;
  }
};

// Video Library API functions

export const getVideoLibrary = async (): Promise<VideoLibraryResponse> => {
  try {
    const response = await apiClient.get<VideoLibraryResponse>(
      "/library/videos"
    );
    return response.data;
  } catch (error) {
    console.error("Error fetching video library:", error);
    throw error;
  }
};

export const getVideoGroups = async (): Promise<VideoGroupsResponse> => {
  try {
    const response = await apiClient.get<VideoGroupsResponse>(
      "/library/videos/grouped"
    );
    return response.data;
  } catch (error) {
    console.error("Error fetching video groups:", error);
    throw error;
  }
};

export const addYouTubeVideo = async (
  url: string,
  model: string = "base"
): Promise<AddVideoResponse> => {
  try {
    const response = await apiClient.post<AddVideoResponse>(
      "/library/videos/youtube",
      { url, model }
    );
    return response.data;
  } catch (error) {
    console.error("Error adding YouTube video:", error);
    throw error;
  }
};

export const uploadVideos = async (
  files: File[],
  model: string = "base"
): Promise<AddVideosResponse> => {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });
  formData.append("model", model);

  try {
    const response = await axios.post<AddVideosResponse>(
      `${API_URL}/library/videos/upload`,
      formData,
      {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      }
    );
    return response.data;
  } catch (error) {
    console.error("Error uploading videos:", error);
    throw error;
  }
};

export const deleteVideo = async (videoId: string): Promise<void> => {
  try {
    await apiClient.delete(`/library/videos/${videoId}`);
  } catch (error) {
    console.error("Error deleting video:", error);
    throw error;
  }
};

export const getProcessingStatus =
  async (): Promise<ProcessingStatusResponse> => {
    try {
      const response = await apiClient.get<ProcessingStatusResponse>(
        "/library/status"
      );
      return response.data;
    } catch (error) {
      console.error("Error fetching processing status:", error);
      throw error;
    }
  };

export const retryVideo = async (videoId: string): Promise<void> => {
  try {
    await apiClient.post(`/library/videos/${videoId}/retry`);
  } catch (error) {
    console.error("Error retrying video:", error);
    throw error;
  }
};

export const getVideoTranscript = async (
  videoId: string
): Promise<VideoTranscriptResponse> => {
  try {
    const response = await apiClient.get<VideoTranscriptResponse>(
      `/library/videos/${videoId}/transcript`
    );
    return response.data;
  } catch (error) {
    console.error("Error fetching video transcript:", error);
    throw error;
  }
};

export const clearLibrary = async (): Promise<{
  message: string;
  deletedCount: number;
  errors: Array<{ videoId: string; error: string }>;
}> => {
  try {
    const response = await apiClient.delete("/library/clear");
    return response.data;
  } catch (error) {
    console.error("Error clearing library:", error);
    throw error;
  }
};

// Helper functions for media URLs
export const getVideoStreamUrl = (videoId: string): string => {
  return `${API_URL}/media/video/${videoId}`;
};

export const getThumbnailUrl = (videoId: string): string => {
  return `${API_URL}/media/thumbnail/${videoId}`;
};
