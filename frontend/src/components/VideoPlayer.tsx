import { useRef, useImperativeHandle, forwardRef, useEffect } from "react";
import type { VideoMetadata } from "../types/library.types";
import { getVideoStreamUrl } from "../services/api";
import YouTubePlayer, { type YouTubePlayerHandle } from "./YouTubePlayer";

export interface VideoPlayerHandle {
  seekTo: (seconds: number) => void;
}

interface VideoPlayerProps {
  video: VideoMetadata | null;
  onTimeUpdate?: (currentTime: number) => void;
}

const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  ({ video, onTimeUpdate }, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const youtubeRef = useRef<YouTubePlayerHandle>(null);

    useImperativeHandle(ref, () => ({
      seekTo: (seconds: number) => {
        if (video?.source === "youtube" && youtubeRef.current) {
          youtubeRef.current.seekTo(seconds);
        } else if (videoRef.current) {
          videoRef.current.currentTime = seconds;
          videoRef.current.play().catch(() => {});
        }
      },
    }));

    useEffect(() => {
      const videoElement = videoRef.current;
      if (!videoElement || !onTimeUpdate) return;

      const handleTimeUpdate = () => {
        onTimeUpdate(videoElement.currentTime);
      };

      videoElement.addEventListener("timeupdate", handleTimeUpdate);
      return () => {
        videoElement.removeEventListener("timeupdate", handleTimeUpdate);
      };
    }, [onTimeUpdate]);

    if (!video) {
      return (
        <div className="h-full aspect-video max-w-full flex items-center justify-center bg-gray-800 text-gray-400 rounded-lg">
          <div className="text-center">
            <svg
              className="w-16 h-16 mx-auto mb-4 text-gray-600"
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
            <p className="text-lg">Select a video from the library</p>
          </div>
        </div>
      );
    }

    if (video.status !== "completed") {
      return (
        <div className="h-full aspect-video max-w-full flex items-center justify-center bg-gray-800 text-gray-400 rounded-lg">
          <div className="text-center">
            {video.status === "processing" ? (
              <>
                <svg
                  className="animate-spin w-12 h-12 mx-auto mb-4 text-indigo-500"
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
                <p className="text-lg">Processing video...</p>
                <p className="text-sm text-gray-500 mt-1">{video.title}</p>
              </>
            ) : video.status === "pending" ? (
              <>
                <svg
                  className="w-12 h-12 mx-auto mb-4 text-yellow-500"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <p className="text-lg">Waiting to process...</p>
                <p className="text-sm text-gray-500 mt-1">{video.title}</p>
              </>
            ) : (
              <>
                <svg
                  className="w-12 h-12 mx-auto mb-4 text-red-500"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
                <p className="text-lg">Processing failed</p>
                <p className="text-sm text-gray-500 mt-1">{video.title}</p>
                {video.errorMessage && (
                  <p className="text-sm text-red-400 mt-2">
                    {video.errorMessage}
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      );
    }

    // YouTube video - use YouTube embed (with aspect ratio container)
    if (video.source === "youtube" && video.youtubeUrl) {
      return (
        <div className="h-full aspect-video bg-black">
          <YouTubePlayer ref={youtubeRef} videoUrl={video.youtubeUrl} />
        </div>
      );
    }

    // Local video - use HTML5 video player
    return (
      <video
        ref={videoRef}
        src={getVideoStreamUrl(video.id)}
        controls
        className="h-full max-w-full bg-black"
        preload="metadata"
      >
        Your browser does not support the video tag.
      </video>
    );
  }
);

VideoPlayer.displayName = "VideoPlayer";

export default VideoPlayer;
