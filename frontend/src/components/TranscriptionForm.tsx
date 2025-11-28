import React, {
  useState,
  useEffect,
  useRef,
  useImperativeHandle,
  forwardRef,
} from "react";
import type {
  WhisperModelType,
  TranscriptionResponse,
} from "../types/transcription.types";
import { transcribeVideoUrl, transcribeVideoFile } from "../services/api";
import YouTubePlayer, { type YouTubePlayerHandle } from "./YouTubePlayer";
import { LoadingIndicatorButton } from "./LoadingIndicatorButton";

interface TranscriptionFormProps {
  onTranscriptionComplete: (result: TranscriptionResponse) => void;
  onError: (error: Error | null) => void;
}

export interface TranscriptionFormHandle {
  seekToTime: (seconds: number) => void;
}

const TranscriptionForm = forwardRef<
  TranscriptionFormHandle,
  TranscriptionFormProps
>(({ onTranscriptionComplete, onError }, ref) => {
  const [videoUrl, setVideoUrl] = useState("");
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoId, setVideoId] = useState<string | null>(null);
  const [videoObjectUrl, setVideoObjectUrl] = useState<string | null>(null);
  const [videoPosterUrl, setVideoPosterUrl] = useState<string | null>(null);
  const [language, setLanguage] = useState<string>("");
  const [model, setModel] = useState<WhisperModelType>("small");
  const [isLoading, setIsLoading] = useState(false);
  const youtubePlayerRef = useRef<YouTubePlayerHandle>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useImperativeHandle(ref, () => ({
    seekToTime: (seconds: number) => {
      if (youtubePlayerRef.current && videoId) {
        // YouTube video
        youtubePlayerRef.current.seekTo(seconds);
      } else if (videoRef.current && videoFile) {
        // Local video file
        videoRef.current.currentTime = seconds;
      }
    },
  }));

  // Cleanup object URLs when component unmounts or file changes
  useEffect(() => {
    return () => {
      if (videoObjectUrl) {
        URL.revokeObjectURL(videoObjectUrl);
      }
      if (videoPosterUrl) {
        URL.revokeObjectURL(videoPosterUrl);
      }
    };
  }, [videoObjectUrl, videoPosterUrl]);

  // Generate video thumbnail
  const generateVideoThumbnail = (videoFile: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const video = document.createElement("video");
      const canvas = document.createElement("canvas");
      const context = canvas.getContext("2d");

      if (!context) {
        reject(new Error("Could not get canvas context"));
        return;
      }

      // Set video properties for better compatibility
      video.crossOrigin = "anonymous";
      video.muted = true; // Helps with autoplay policies
      video.playsInline = true;

      let hasSeekCompleted = false;

      video.addEventListener("loadeddata", () => {
        console.log(
          "Video loaded, dimensions:",
          video.videoWidth,
          "x",
          video.videoHeight
        );

        // Set canvas dimensions to video dimensions
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        if (canvas.width === 0 || canvas.height === 0) {
          reject(new Error("Invalid video dimensions"));
          return;
        }

        // Seek to 1 second or 10% of video duration, whichever is smaller
        const seekTime = Math.min(1, video.duration * 0.1) || 0.5;
        console.log("Seeking to time:", seekTime);
        video.currentTime = seekTime;
      });

      video.addEventListener("seeked", () => {
        if (hasSeekCompleted) return; // Prevent multiple calls
        hasSeekCompleted = true;

        console.log("Seek completed, drawing frame...");

        // Small delay to ensure frame is ready
        setTimeout(() => {
          try {
            // Draw the video frame to canvas
            context.drawImage(video, 0, 0, canvas.width, canvas.height);

            // Convert canvas to blob
            canvas.toBlob(
              (blob) => {
                if (blob) {
                  const thumbnailUrl = URL.createObjectURL(blob);
                  console.log("Thumbnail generated successfully");
                  resolve(thumbnailUrl);
                } else {
                  reject(new Error("Failed to generate thumbnail blob"));
                }
              },
              "image/jpeg",
              0.8
            );
          } catch (error) {
            reject(new Error(`Failed to draw video frame: ${error}`));
          }
        }, 100);
      });

      video.addEventListener("error", (e) => {
        console.error("Video error:", e);
        reject(new Error("Failed to load video for thumbnail generation"));
      });

      // Set video source and load
      video.src = URL.createObjectURL(videoFile);
      video.load();
    });
  };

  // Extract YouTube video ID from various URL formats
  const extractVideoId = (url: string): string | null => {
    const patterns = [
      /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&?/]+)/i,
      /youtube\.com\/watch\?.*v=([^&]+)/i,
    ];

    for (const pattern of patterns) {
      const match = url.match(pattern);
      if (match && match[1]) {
        return match[1];
      }
    }

    return null;
  };

  // Show the YouTube player when a valid URL is entered
  useEffect(() => {
    let id = null;
    if (videoUrl.includes("youtube.com") || videoUrl.includes("youtu.be")) {
      id = extractVideoId(videoUrl);
      setVideoId(id);
    } else {
      setVideoId(id);
    }

    // Only validate URL if it's not a filename from a selected file
    if (videoUrl && (!videoFile || videoUrl !== videoFile.name)) {
      if (!id) {
        onError(new Error("Invalid YouTube URL"));
      } else {
        onError(null); // Clear errors for valid URLs
      }
    }
  }, [videoUrl, videoFile, onError]);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      console.log("File details:", {
        name: file.name,
        type: file.type,
        size: file.size,
      });

      // Validate file type - check both MIME type and file extension
      const allowedMimeTypes = [
        "video/mp4",
        "video/avi",
        "video/mov",
        "video/quicktime",
        "video/x-msvideo",
        "video/mkv",
        "video/webm",
      ];
      const allowedExtensions = [".mp4", ".avi", ".mov", ".mkv", ".webm"];
      const fileExtension = file.name
        .toLowerCase()
        .substring(file.name.lastIndexOf("."));

      const isValidMimeType = allowedMimeTypes.includes(file.type);
      const isValidExtension = allowedExtensions.includes(fileExtension);

      if (!isValidMimeType && !isValidExtension) {
        onError(
          new Error(
            `Please select a valid video file (MP4, AVI, MOV, MKV, WebM). Selected file type: ${file.type || "unknown"}`
          )
        );
        // Reset file input
        e.target.value = "";
        return;
      }

      // Validate file size (50MB limit)
      const maxSize = 50 * 1024 * 1024; // 50MB
      if (file.size > maxSize) {
        onError(new Error("File size must be less than 50MB"));
        // Reset file input
        e.target.value = "";
        return;
      }

      // Clean up previous URLs
      if (videoObjectUrl) {
        URL.revokeObjectURL(videoObjectUrl);
      }
      if (videoPosterUrl) {
        URL.revokeObjectURL(videoPosterUrl);
      }

      // Use FileReader for better Safari compatibility
      const reader = new FileReader();
      reader.onloadend = () => {
        const dataUrl = reader.result as string;
        setVideoObjectUrl(dataUrl);
      };
      reader.onerror = () => {
        console.error("Failed to read file");
        onError(new Error("Failed to read video file"));
      };
      reader.readAsDataURL(file);

      setVideoFile(file);
      setVideoUrl(file.name); // Show filename in URL field
      setVideoId(null); // Clear YouTube player
      onError(null); // Clear any previous errors

      // Generate thumbnail asynchronously
      try {
        const thumbnailUrl = await generateVideoThumbnail(file);
        setVideoPosterUrl(thumbnailUrl);
      } catch (error) {
        console.warn("Failed to generate video thumbnail:", error);
        // Don't show error to user, just proceed without thumbnail
      }
    } else {
      // File was cleared/unselected
      if (videoObjectUrl) {
        URL.revokeObjectURL(videoObjectUrl);
        setVideoObjectUrl(null);
      }
      if (videoPosterUrl) {
        URL.revokeObjectURL(videoPosterUrl);
        setVideoPosterUrl(null);
      }
      setVideoFile(null);
      if (videoUrl === videoFile?.name) {
        setVideoUrl(""); // Clear the filename from URL field
      }
    }
  };

  const handleUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const url = e.target.value;
    setVideoUrl(url);
    if (url !== videoFile?.name) {
      // If user is typing a URL (not the filename), clear the file
      if (videoObjectUrl) {
        URL.revokeObjectURL(videoObjectUrl);
        setVideoObjectUrl(null);
      }
      if (videoPosterUrl) {
        URL.revokeObjectURL(videoPosterUrl);
        setVideoPosterUrl(null);
      }
      setVideoFile(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      let response;

      // Determine which input method to use based on what the user provided
      if (videoFile) {
        // File upload takes priority if both are provided
        response = await transcribeVideoFile(videoFile, model, language);
      } else if (videoUrl.trim()) {
        // Use URL if provided
        response = await transcribeVideoUrl(videoUrl, model, language);
      } else {
        throw new Error(
          "Please provide either a YouTube URL or upload a video file"
        );
      }

      onTranscriptionComplete(response);
    } catch (error) {
      console.error("Error during transcription:", error);
      onError(
        error instanceof Error ? error : new Error("An unknown error occurred")
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-4 p-6 bg-white rounded-lg shadow-md"
    >
      {/* Unified Input */}
      <div>
        <label
          htmlFor="videoUrl"
          className="block text-sm font-medium text-gray-700"
        >
          Video Source
        </label>
        <div className="mt-1 flex gap-2">
          <input
            type="text"
            id="videoUrl"
            value={videoUrl}
            onChange={handleUrlChange}
            placeholder="Enter YouTube URL or choose a file..."
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
            readOnly={!!videoFile}
          />
          <label
            htmlFor="videoFile"
            className="inline-flex items-center px-4 py-2 bg-indigo-50 border border-indigo-300 rounded-md text-sm font-medium text-indigo-700 hover:bg-indigo-100 cursor-pointer transition-colors"
          >
            📁 Browse
            <input
              type="file"
              id="videoFile"
              accept="video/*"
              onChange={handleFileChange}
              className="sr-only"
            />
          </label>
        </div>
      </div>

      {/* Video preview container - shown for both URLs and files */}
      {(videoUrl || videoFile) && (
        <div
          className="mt-4 bg-gray-50 rounded-md"
          style={{
            minHeight: "315px",
            transition: "min-height 0.3s ease-in-out",
          }}
        >
          {videoFile && videoObjectUrl ? (
            // Local video player
            <div className="p-4">
              <video
                ref={videoRef}
                controls
                className="w-full h-full rounded-md"
                style={{ maxHeight: "315px" }}
                preload="metadata"
                poster={videoPosterUrl || undefined}
                src={videoObjectUrl}
              >
                Your browser does not support the video tag.
              </video>
              <div className="mt-2 text-center">
                <p className="text-sm text-gray-600">
                  {videoFile.name} • {(videoFile.size / 1024 / 1024).toFixed(2)}{" "}
                  MB
                </p>
              </div>
            </div>
          ) : videoId ? (
            // YouTube player
            <div className="p-4">
              <YouTubePlayer ref={youtubePlayerRef} videoUrl={videoUrl} />
            </div>
          ) : (
            // Invalid URL message
            <div className="p-4 flex items-center justify-center h-full">
              <p className="text-gray-400">
                Enter a valid YouTube URL to see the video player
              </p>
            </div>
          )}
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label
            htmlFor="language"
            className="block text-sm font-medium text-gray-700"
          >
            Language
          </label>
          <select
            id="language"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
          >
            <option value="">(Auto)</option>
            <option value="de">German</option>
            <option value="en">English</option>
            <option value="fr">French</option>
            <option value="es">Spanish</option>
          </select>
        </div>
        <div>
          <label
            htmlFor="model"
            className="block text-sm font-medium text-gray-700"
          >
            Whisper Model
          </label>
          <select
            id="model"
            value={model}
            onChange={(e) => {
              const selectedModel = e.target.value as WhisperModelType;
              if (selectedModel) {
                setModel(selectedModel);
              }
            }}
            className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
          >
            <option value="tiny">Tiny (Fastest)</option>
            <option value="base">Base</option>
            <option value="small">Small</option>
            <option value="medium">Medium</option>
            <option value="large">Large (Most Accurate)</option>
            <option value="turbo">Turbo</option>
          </select>
        </div>
      </div>
      <LoadingIndicatorButton
        isLoading={isLoading}
        buttonText="Transcribe Video"
      />
    </form>
  );
});

TranscriptionForm.displayName = "TranscriptionForm";

export default TranscriptionForm;
