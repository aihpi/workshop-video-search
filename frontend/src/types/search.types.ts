export type SearchType = "keyword" | "semantic" | "llm" | "visual";

export const SearchTypeNames: Record<SearchType, string> = {
  keyword: "Keyword Search",
  semantic: "Semantic Search",
  llm: "LLM Synthesis",
  visual: "Visual Search",
};

export type QuestionRequest = {
  question: string;
  videoIds?: string[]; // List of video IDs to search (null = all videos)
  topK?: number;
  searchType?: SearchType;
};

export type SegmentResult = {
  segmentId: string;
  startTime: number;
  endTime: number;
  text: string;
  videoId: string;
  videoTitle: string | null;
  relevanceScore: number | null;
  frameTimestamp: number | null;
  framePath: string | null;
  searchType: SearchType | null;
};

export type LlmAnswer = {
  summary: string;
  notAddressed: boolean;
  modelId: string;
};

export type BaseSearchResponse = {
  question: string;
  videoIds?: string[]; // Video IDs that were searched
  results: SegmentResult[];
  searchType: SearchType;
};

export type KeywordSearchResponse = BaseSearchResponse & {
  searchType: "keyword";
};

export type SemanticSearchResponse = BaseSearchResponse & {
  searchType: "semantic";
};

export type LlmSearchResponse = BaseSearchResponse &
  LlmAnswer & {
    searchType: "llm";
  };

export type VisualSearchResponse = BaseSearchResponse & {
  searchType: "visual";
};

export type QuestionResponse =
  | KeywordSearchResponse
  | SemanticSearchResponse
  | LlmSearchResponse
  | VisualSearchResponse;
