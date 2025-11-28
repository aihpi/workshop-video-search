import React, { useState } from "react";
import { type TranscriptionResponse } from "../types/transcription.types";
import {
  type SegmentResult,
  type SearchType,
  SearchTypeNames,
} from "../types/search.types";
import { queryTranscript } from "../services/api";
import { LoadingIndicatorButton } from "./LoadingIndicatorButton";
import LLMDropdown from "./LLMDropdown";
import SummarizationPanel from "./SummarizationPanel";
import type { LlmAnswer } from "../types/search.types";

interface TranscriptionResultProps {
  transcriptionResponse: TranscriptionResponse;
  onSeekToTime?: (seconds: number) => void;
  onError?: (error: Error | null) => void;
}

const TranscriptionResult: React.FC<TranscriptionResultProps> = ({
  transcriptionResponse,
  onSeekToTime,
  onError,
}) => {
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSegment, setActiveSegment] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SearchType>("keyword");
  
  // Get API URL for constructing frame URLs
  const API_URL = import.meta.env.VITE_API_URL || "http://localhost:9091";

  // State for storing results from different search methods
  const [keywordResults, setKeywordResults] = useState<SegmentResult[]>([]);
  const [semanticResults, setSemanticResults] = useState<SegmentResult[]>([]);
  const [llmResults, setLlmResults] = useState<SegmentResult[]>([]);
  const [visualResults, setVisualResults] = useState<SegmentResult[]>([]);
  const [llmAnswer, setLlmAnswer] = useState<LlmAnswer | null>(null);

  // Track which search methods have been used so far
  const [searchesPerformed, setSearchesPerformed] = useState<{
    keyword: boolean;
    semantic: boolean;
    llm: boolean;
    visual: boolean;
  }>({
    keyword: false,
    semantic: false,
    llm: false,
    visual: false,
  });

  // Get results for the current active tab
  const getActiveTabResults = () => {
    switch (activeTab) {
      case "keyword":
        return keywordResults;
      case "semantic":
        return semanticResults;
      case "llm":
        return llmResults;
      case "visual":
        return visualResults;
      default:
        return [];
    }
  };

  // Get initial segments as SegmentResult objects
  const getInitialSegmentResults = (): SegmentResult[] => {
    return transcriptionResponse.segments.map((segment) => {
      return {
        startTime: segment.start,
        endTime: segment.end,
        text: segment.text,
        segmentId: segment.id,
        videoId: transcriptionResponse.id,
        videoTitle: null,
        relevanceScore: null,
        frameTimestamp: null,
        framePath: null,
        searchType: null,
      } as SegmentResult;
    });
  };

  const formatTime = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds < 10 ? "0" : ""}${remainingSeconds}`;
  };

  const handleQueryTranscript = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;

    setIsLoading(true);
    setError(null);

    console.log("Question:", question, "Search type:", activeTab);
    try {
      const response = await queryTranscript(
        question,
        [transcriptionResponse.id],
        5,
        activeTab
      );
      console.log("Query response:", response);

      // Store results in the appropriate state variable
      if (response.searchType === "keyword") {
        setKeywordResults(response.results);
        setSearchesPerformed((prev) => ({ ...prev, keyword: true }));
      } else if (response.searchType === "semantic") {
        setSemanticResults(response.results);
        setSearchesPerformed((prev) => ({ ...prev, semantic: true }));
      } else if (response.searchType === "llm") {
        setLlmResults(response.results);
        setLlmAnswer({
          summary: response.summary,
          notAddressed: response.notAddressed,
          modelId: response.modelId,
        });
        setSearchesPerformed((prev) => ({ ...prev, llm: true }));
      } else if (response.searchType === "visual") {
        setVisualResults(response.results);
        setSearchesPerformed((prev) => ({ ...prev, visual: true }));
      }

      setActiveSegment(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");

      // Clear results for the current tab on error
      if (activeTab === "keyword") {
        setKeywordResults([]);
      } else if (activeTab === "semantic") {
        setSemanticResults([]);
      } else if (activeTab === "llm") {
        setLlmResults([]);
        setLlmAnswer(null);
      } else if (activeTab === "visual") {
        setVisualResults([]);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleResultClick = (segment: SegmentResult) => {
    if (onSeekToTime) {
      onSeekToTime(segment.startTime);
    }
    setActiveSegment(segment.segmentId);
  };

  const handleClearSearch = () => {
    setQuestion("");
    setKeywordResults([]);
    setSemanticResults([]);
    setLlmResults([]);
    setLlmAnswer(null);
    setSearchesPerformed({
      keyword: false,
      semantic: false,
      llm: false,
      visual: false,
    });
    setVisualResults([]);
    setActiveSegment(null);
    setError(null);
  };

  const handleTabChange = (tab: SearchType) => {
    setActiveTab(tab);
    setActiveSegment(null);
    setError(null);
  };

  const currentResults: () => SegmentResult[] = () => {
    const activeTabResults = getActiveTabResults();
    if (activeTabResults.length > 0) {
      return activeTabResults;
    }
    if (!searchesPerformed[activeTab]) {
      return getInitialSegmentResults();
    }
    return [];
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 space-y-6">
      <div className="flex items-center flex-col">
        <h2 className="text-xl font-semibold text-gray-800 text-center flex-1 mb-4">
          Transcription
        </h2>
        <form onSubmit={handleQueryTranscript} className="mb-2 w-full">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder={`Search using ${SearchTypeNames[activeTab]}`}
                className="w-full px-3 py-2 pr-8 border border-gray-300 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                disabled={isLoading}
              />

              {question && !isLoading && (
                <div
                  className="absolute inset-y-0 right-0 pr-3 flex items-center cursor-pointer"
                  onClick={() => handleClearSearch()}
                  role="button"
                  tabIndex={0}
                  aria-label="Clear search"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-4 w-4 text-gray-400 hover:text-gray-600"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </div>
              )}
            </div>
            <LoadingIndicatorButton
              isLoading={isLoading}
              buttonText="Search"
              disabled={isLoading || !question.trim()}
            />
          </div>
        </form>
      </div>

      {/* Segments */}
      <div>
        <div className="bg-gray-50 p-4 rounded-md space-y-2 max-h-96 overflow-y-auto">
          {/* Search Type Tabs */}
          <div className="flex border-b border-gray-200 mb-4">
            {(Object.keys(SearchTypeNames) as SearchType[]).map(
              (searchType, index) => (
                <button
                  key={searchType}
                  onClick={() => handleTabChange(searchType)}
                  className={`px-4 py-2 text-sm font-medium ${index > 0 ? "ml-4" : ""} ${
                    activeTab === searchType
                      ? "text-indigo-600 border-b-2 border-indigo-600"
                      : "text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {SearchTypeNames[searchType]}{" "}
                  {searchesPerformed[searchType] && "✓"}
                </button>
              )
            )}
          </div>

          {/* LLM Model Selection - Only shown for AI Synthesis */}
          {activeTab === "llm" && (
            <div className="mb-4">
              <LLMDropdown
                onError={(error) => setError(error?.message || null)}
              />
            </div>
          )}

          {/* LLM Answer Display */}
          {activeTab === "llm" && llmAnswer && (
            <div className="mb-4 p-4 bg-blue-50 rounded-md border border-blue-200">
              <h3 className="font-semibold text-lg mb-2">AI Summary</h3>
              <p className="text-gray-700 mb-3">{llmAnswer.summary}</p>

              {llmAnswer.notAddressed && (
                <p className="text-sm text-orange-600 mt-2">
                  ⚠️ Some aspects of your question could not be answered from
                  the transcript.
                </p>
              )}
            </div>
          )}

          {currentResults().length > 0 &&
            currentResults().map((result: SegmentResult) => (
              <div
                key={result.segmentId}
                className={`p-3 rounded-md cursor-pointer ${
                  activeSegment === result.segmentId
                    ? "bg-indigo-50 border border-indigo-200"
                    : "bg-white border border-gray-200"
                }`}
                onClick={() => handleResultClick(result)}
              >
                <div className="flex gap-3">
                  {/* Frame thumbnail for visual search results */}
                  {result.framePath && activeTab === "visual" && (
                    <div className="flex-shrink-0">
                      <img
                        src={`${API_URL}${result.framePath}`}
                        alt={`Frame at ${result.frameTimestamp}s`}
                        className="w-32 h-20 object-cover rounded-md border border-gray-200 hover:border-indigo-300 transition-colors cursor-pointer"
                        loading="lazy"
                        onClick={(e) => {
                          e.stopPropagation(); // Prevent parent div click
                          window.open(`${API_URL}${result.framePath}`, "_blank");
                        }}
                        onError={(e) => {
                          // Hide image if it fails to load
                          (e.target as HTMLImageElement).style.display = "none";
                        }}
                      />
                    </div>
                  )}

                  <div className="flex-1">
                    <div className="flex justify-between text-sm text-gray-500 mb-1">
                      <span>
                        {formatTime(result.startTime)} -{" "}
                        {formatTime(result.endTime)}
                      </span>
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-1 rounded-md text-xs font-medium">
                          {result.relevanceScore
                            ? `${result.relevanceScore}%`
                            : " "}
                        </span>
                      </div>
                    </div>
                    <p className="text-gray-800">{result.text}</p>
                  </div>
                </div>
              </div>
            ))}

          {currentResults().length === 0 &&
            !isLoading &&
            !error &&
            question && (
              <p className="text-sm text-gray-500">
                No relevant segments found for your question.
              </p>
            )}
        </div>
      </div>

      <SummarizationPanel
        videoId={transcriptionResponse.id}
        onError={onError || (() => {})}
      />
    </div>
  );
};

export default TranscriptionResult;
