import React, { useState, useMemo, useEffect } from "react";
import type {
  VideoMetadata,
  TranscriptSegment,
} from "../types/library.types";
import {
  type SegmentResult,
  type SearchType,
  SearchTypeNames,
  type LlmAnswer,
} from "../types/search.types";
import { queryTranscript, getVideoTranscript, API_URL } from "../services/api";
import { LoadingIndicatorButton } from "./LoadingIndicatorButton";
import LLMDropdown from "./LLMDropdown";

interface SearchPanelProps {
  selectedVideo: VideoMetadata | null;
  allVideoIds: string[];
  onSeekToTime: (seconds: number, videoId?: string) => void;
  onError: (error: Error | null) => void;
}

type SearchScope = "all" | "current";

const MAX_RESULTS_PER_VIDEO = 3;

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
};

const SearchPanel: React.FC<SearchPanelProps> = ({
  selectedVideo,
  allVideoIds,
  onSeekToTime,
  onError,
}) => {
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [searchScope, setSearchScope] = useState<SearchScope>("all");
  const [activeTab, setActiveTab] = useState<SearchType>("semantic");
  const [results, setResults] = useState<SegmentResult[]>([]);
  const [llmAnswer, setLlmAnswer] = useState<LlmAnswer | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  // Transcript state for default view
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [isLoadingTranscript, setIsLoadingTranscript] = useState(false);

  // Fetch transcript when selected video changes
  useEffect(() => {
    if (selectedVideo && selectedVideo.status === "completed") {
      setIsLoadingTranscript(true);
      getVideoTranscript(selectedVideo.id)
        .then((response) => {
          setTranscript(response.segments);
        })
        .catch((err) => {
          console.error("Failed to fetch transcript:", err);
          setTranscript([]);
        })
        .finally(() => {
          setIsLoadingTranscript(false);
        });
    } else {
      setTranscript([]);
    }
  }, [selectedVideo?.id, selectedVideo?.status]);

  // Group results by video
  const groupedResults = useMemo(() => {
    const groups: Record<
      string,
      { videoTitle: string; results: SegmentResult[] }
    > = {};

    for (const result of results) {
      const videoId = result.videoId;
      if (!groups[videoId]) {
        groups[videoId] = {
          videoTitle: result.videoTitle || videoId,
          results: [],
        };
      }
      // Limit to MAX_RESULTS_PER_VIDEO per video
      if (groups[videoId].results.length < MAX_RESULTS_PER_VIDEO) {
        groups[videoId].results.push(result);
      }
    }

    return Object.entries(groups);
  }, [results]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;

    // Determine which video IDs to search
    let videoIdsToSearch: string[] | null = null;
    if (searchScope === "current" && selectedVideo) {
      videoIdsToSearch = [selectedVideo.id];
    } else if (searchScope === "all" && allVideoIds.length > 0) {
      videoIdsToSearch = null; // null means search all
    }

    if (searchScope === "current" && !selectedVideo) {
      onError(new Error("Please select a video first"));
      return;
    }

    if (allVideoIds.length === 0) {
      onError(new Error("No videos available to search"));
      return;
    }

    setIsLoading(true);
    setHasSearched(true);
    onError(null);

    try {
      const response = await queryTranscript(
        question,
        videoIdsToSearch,
        15, // Fetch more results to allow grouping
        activeTab
      );

      setResults(response.results);

      if (response.searchType === "llm") {
        setLlmAnswer({
          summary: (response as any).summary,
          notAddressed: (response as any).notAddressed,
          modelId: (response as any).modelId,
        });
      } else {
        setLlmAnswer(null);
      }
    } catch (err) {
      onError(err instanceof Error ? err : new Error("Search failed"));
      setResults([]);
      setLlmAnswer(null);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClear = () => {
    setQuestion("");
    setResults([]);
    setLlmAnswer(null);
    setHasSearched(false);
    onError(null);
  };

  const handleResultClick = (result: SegmentResult) => {
    onSeekToTime(result.startTime, result.videoId);
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Search Header */}
      <div className="flex-shrink-0 p-4 border-b border-gray-200">
        <form onSubmit={handleSearch} className="space-y-3">
          {/* Search input */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder={`Search using ${SearchTypeNames[activeTab]}...`}
                className="w-full px-4 py-2 pr-10 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                disabled={isLoading}
              />
              {question && !isLoading && (
                <button
                  type="button"
                  onClick={handleClear}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              )}
            </div>
            <LoadingIndicatorButton
              isLoading={isLoading}
              buttonText="Search"
              disabled={isLoading || !question.trim()}
            />
          </div>

          {/* Search scope toggle */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <span className="text-sm text-gray-500">Search in:</span>
              <div className="flex rounded-lg border border-gray-300 overflow-hidden">
                <button
                  type="button"
                  onClick={() => setSearchScope("all")}
                  className={`px-3 py-1 text-sm ${
                    searchScope === "all"
                      ? "bg-indigo-600 text-white"
                      : "bg-white text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  All Videos
                </button>
                <button
                  type="button"
                  onClick={() => setSearchScope("current")}
                  disabled={!selectedVideo}
                  className={`px-3 py-1 text-sm border-l border-gray-300 ${
                    searchScope === "current"
                      ? "bg-indigo-600 text-white"
                      : "bg-white text-gray-700 hover:bg-gray-50"
                  } ${!selectedVideo ? "opacity-50 cursor-not-allowed" : ""}`}
                >
                  Current Video
                </button>
              </div>
            </div>

            {/* LLM selector for AI Synthesis */}
            {activeTab === "llm" && (
              <LLMDropdown onError={(err) => onError(err)} />
            )}
          </div>
        </form>

        {/* Search Type Tabs */}
        <div className="flex border-b border-gray-200 mt-4 -mb-px">
          {(Object.keys(SearchTypeNames) as SearchType[]).map((searchType) => (
            <button
              key={searchType}
              onClick={() => setActiveTab(searchType)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === searchType
                  ? "text-indigo-600 border-indigo-600"
                  : "text-gray-500 border-transparent hover:text-gray-700 hover:border-gray-300"
              }`}
            >
              {SearchTypeNames[searchType]}
            </button>
          ))}
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* LLM Answer */}
        {activeTab === "llm" && llmAnswer && (
          <div className="mb-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
            <h3 className="font-semibold text-lg mb-2 text-blue-900">
              AI Summary
            </h3>
            <p className="text-gray-700">{llmAnswer.summary}</p>
            {llmAnswer.notAddressed && (
              <p className="mt-2 text-sm text-orange-600">
                Some aspects of your question could not be answered from the
                transcripts.
              </p>
            )}
          </div>
        )}

        {/* Grouped Results (Search Mode) */}
        {hasSearched && groupedResults.length > 0 ? (
          <div className="space-y-4">
            {groupedResults.map(([videoId, { videoTitle, results: videoResults }]) => (
              <div key={videoId} className="border border-gray-200 rounded-lg overflow-hidden">
                {/* Video header */}
                <div className="bg-gray-50 px-4 py-2 border-b border-gray-200">
                  <div className="flex items-center gap-2">
                    <svg
                      className="w-5 h-5 text-gray-500"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                      />
                    </svg>
                    <span className="font-medium text-gray-900">
                      {videoTitle}
                    </span>
                    <span className="text-sm text-gray-500">
                      ({videoResults.length} match{videoResults.length !== 1 ? "es" : ""})
                    </span>
                  </div>
                </div>

                {/* Results for this video */}
                <div className="divide-y divide-gray-100">
                  {videoResults.map((result) => (
                    <div
                      key={result.segmentId}
                      className="p-3 hover:bg-gray-50 cursor-pointer transition-colors"
                      onClick={() => handleResultClick(result)}
                    >
                      <div className="flex gap-3">
                        {/* Frame thumbnail for visual search */}
                        {result.framePath && activeTab === "visual" && (
                          <div className="flex-shrink-0">
                            <img
                              src={`${API_URL}${result.framePath}`}
                              alt={`Frame at ${result.frameTimestamp}s`}
                              className="w-24 h-16 object-cover rounded border border-gray-200"
                              loading="lazy"
                              onError={(e) => {
                                (e.target as HTMLImageElement).style.display =
                                  "none";
                              }}
                            />
                          </div>
                        )}

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm text-indigo-600 font-medium">
                              {formatTime(result.startTime)} -{" "}
                              {formatTime(result.endTime)}
                            </span>
                            <div className="flex items-center gap-2">
                              {result.relevanceScore && (
                                <span className="text-sm text-gray-500">
                                  {result.relevanceScore}%
                                </span>
                              )}
                            </div>
                          </div>
                          <p className="text-gray-700 text-sm line-clamp-2">
                            {result.text}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : hasSearched && !isLoading ? (
          <div className="text-center py-8 text-gray-500">
            <svg
              className="w-12 h-12 mx-auto mb-4 text-gray-300"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <p>No results found for "{question}"</p>
            <p className="text-sm mt-1">Try a different search term or search type</p>
          </div>
        ) : !hasSearched && selectedVideo && transcript.length > 0 ? (
          /* Transcript View (Default when video selected, no search) */
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-gray-700">
                Transcript ({transcript.length} segments)
              </h3>
            </div>
            <div className="border border-gray-200 rounded-lg overflow-hidden divide-y divide-gray-100">
              {transcript.map((segment) => (
                <div
                  key={segment.segmentId}
                  className="p-3 hover:bg-gray-50 cursor-pointer transition-colors"
                  onClick={() => onSeekToTime(segment.startTime)}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-indigo-600 font-medium">
                      {formatTime(segment.startTime)} - {formatTime(segment.endTime)}
                    </span>
                  </div>
                  <p className="text-gray-700 text-sm">{segment.text}</p>
                </div>
              ))}
            </div>
          </div>
        ) : !hasSearched && selectedVideo && isLoadingTranscript ? (
          <div className="text-center py-8 text-gray-500">
            <svg
              className="w-8 h-8 mx-auto mb-4 text-gray-300 animate-spin"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            <p>Loading transcript...</p>
          </div>
        ) : !hasSearched ? (
          <div className="text-center py-8 text-gray-500">
            <svg
              className="w-12 h-12 mx-auto mb-4 text-gray-300"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <p>
              {selectedVideo
                ? "No transcript available"
                : "Select a video to view its transcript"}
            </p>
            <p className="text-sm mt-1">
              Or search across{" "}
              {searchScope === "all"
                ? `${allVideoIds.length} videos`
                : "the current video"}
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default SearchPanel;
