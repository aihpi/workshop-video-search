import React, { useState } from "react";
import type {
  VideoMetadata,
  VideosByGroup,
  ProcessingStatus,
} from "../types/library.types";
import { getThumbnailUrl, deleteVideo, retryVideo, clearLibrary } from "../services/api";

interface VideoLibraryProps {
  groups: VideosByGroup[];
  selectedVideoId: string | null;
  onSelectVideo: (video: VideoMetadata) => void;
  onAddVideos: () => void;
  onRefresh: () => void;
  processingCount: number;
}

const StatusBadge: React.FC<{ status: ProcessingStatus }> = ({ status }) => {
  const statusConfig = {
    pending: { bg: "bg-yellow-100", text: "text-yellow-800", label: "Pending" },
    processing: {
      bg: "bg-blue-100",
      text: "text-blue-800",
      label: "Processing",
    },
    completed: {
      bg: "bg-green-100",
      text: "text-green-800",
      label: "Ready",
    },
    failed: { bg: "bg-red-100", text: "text-red-800", label: "Failed" },
  };

  const config = statusConfig[status];

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${config.bg} ${config.text}`}
    >
      {status === "processing" && (
        <svg
          className="animate-spin -ml-0.5 mr-1 h-3 w-3"
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
      )}
      {config.label}
    </span>
  );
};

const formatDuration = (seconds: number | null): string => {
  if (!seconds) return "--:--";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  if (mins >= 60) {
    const hours = Math.floor(mins / 60);
    const remainingMins = mins % 60;
    return `${hours}:${remainingMins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${mins}:${secs.toString().padStart(2, "0")}`;
};

const VideoCard: React.FC<{
  video: VideoMetadata;
  isSelected: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onRetry: () => void;
}> = ({ video, isSelected, onSelect, onDelete, onRetry }) => {
  const [showMenu, setShowMenu] = useState(false);
  const [imageError, setImageError] = useState(false);

  return (
    <div
      className={`relative p-2 rounded-md cursor-pointer transition-colors ${
        isSelected
          ? "bg-indigo-100 border-2 border-indigo-500"
          : "bg-white border border-gray-200 hover:bg-gray-50"
      }`}
      onClick={onSelect}
    >
      <div className="flex gap-2">
        {/* Thumbnail */}
        <div className="flex-shrink-0 w-20 h-14 bg-gray-200 rounded overflow-hidden">
          {video.thumbnailPath && !imageError ? (
            <img
              src={getThumbnailUrl(video.id)}
              alt={video.title}
              className="w-full h-full object-cover"
              onError={() => setImageError(true)}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-400">
              <svg
                className="w-6 h-6"
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
            </div>
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate">
            {video.title}
          </p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-gray-500">
              {formatDuration(video.duration)}
            </span>
            <StatusBadge status={video.status} />
          </div>
        </div>

        {/* Menu button */}
        <div className="relative">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowMenu(!showMenu);
            }}
            className="p-1 rounded hover:bg-gray-200"
          >
            <svg
              className="w-4 h-4 text-gray-500"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
            </svg>
          </button>

          {showMenu && (
            <div className="absolute right-0 mt-1 w-32 bg-white rounded-md shadow-lg border border-gray-200 z-10">
              {video.status === "failed" && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onRetry();
                    setShowMenu(false);
                  }}
                  className="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  Retry
                </button>
              )}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete();
                  setShowMenu(false);
                }}
                className="block w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
              >
                Delete
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Error message */}
      {video.status === "failed" && video.errorMessage && (
        <p className="mt-1 text-xs text-red-600 truncate">
          {video.errorMessage}
        </p>
      )}
    </div>
  );
};

const VideoLibrary: React.FC<VideoLibraryProps> = ({
  groups,
  selectedVideoId,
  onSelectVideo,
  onAddVideos,
  onRefresh,
  processingCount,
}) => {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    new Set(groups.map((g) => g.name))
  );

  const toggleGroup = (groupName: string) => {
    const newExpanded = new Set(expandedGroups);
    if (newExpanded.has(groupName)) {
      newExpanded.delete(groupName);
    } else {
      newExpanded.add(groupName);
    }
    setExpandedGroups(newExpanded);
  };

  const handleDelete = async (videoId: string) => {
    if (!confirm("Are you sure you want to delete this video?")) return;
    try {
      await deleteVideo(videoId);
      onRefresh();
    } catch (error) {
      console.error("Error deleting video:", error);
    }
  };

  const handleRetry = async (videoId: string) => {
    try {
      await retryVideo(videoId);
      onRefresh();
    } catch (error) {
      console.error("Error retrying video:", error);
    }
  };

  const handleClearLibrary = async () => {
    if (
      !confirm(
        "Are you sure you want to clear the entire library? This will delete all videos, transcripts, and search data. This action cannot be undone."
      )
    )
      return;
    try {
      await clearLibrary();
      onRefresh();
    } catch (error) {
      console.error("Error clearing library:", error);
    }
  };

  const totalVideos = groups.reduce((sum, g) => sum + g.videos.length, 0);

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 bg-white">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-semibold text-gray-900">Video Library</h2>
          <div className="flex items-center gap-1">
            <button
              onClick={onRefresh}
              className="p-1 rounded hover:bg-gray-100"
              title="Refresh"
            >
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
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
            </button>
            {totalVideos > 0 && (
              <button
                onClick={handleClearLibrary}
                className="p-1 rounded hover:bg-red-100"
                title="Clear Library"
              >
                <svg
                  className="w-5 h-5 text-gray-500 hover:text-red-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                  />
                </svg>
              </button>
            )}
          </div>
        </div>
        <button
          onClick={onAddVideos}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition-colors"
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
              d="M12 4v16m8-8H4"
            />
          </svg>
          Add Videos
        </button>
        {processingCount > 0 && (
          <p className="mt-2 text-sm text-blue-600">
            {processingCount} video(s) processing...
          </p>
        )}
      </div>

      {/* Video list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {totalVideos === 0 ? (
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
                d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
              />
            </svg>
            <p>No videos yet</p>
            <p className="text-sm mt-1">Click "Add Videos" to get started</p>
          </div>
        ) : (
          groups.map(
            (group) =>
              group.videos.length > 0 && (
                <div key={group.name} className="space-y-1">
                  <button
                    onClick={() => toggleGroup(group.name)}
                    className="flex items-center gap-2 w-full text-left px-2 py-1 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded"
                  >
                    <svg
                      className={`w-4 h-4 transition-transform ${
                        expandedGroups.has(group.name) ? "rotate-90" : ""
                      }`}
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path
                        fillRule="evenodd"
                        d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                    {group.name} ({group.videos.length})
                  </button>
                  {expandedGroups.has(group.name) && (
                    <div className="space-y-1 ml-2">
                      {group.videos.map((video) => (
                        <VideoCard
                          key={video.id}
                          video={video}
                          isSelected={selectedVideoId === video.id}
                          onSelect={() => onSelectVideo(video)}
                          onDelete={() => handleDelete(video.id)}
                          onRetry={() => handleRetry(video.id)}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )
          )
        )}
      </div>
    </div>
  );
};

export default VideoLibrary;
