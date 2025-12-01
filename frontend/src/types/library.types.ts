export type ProcessingStatus = "pending" | "processing" | "completed" | "failed";

export type VideoSource = "youtube" | "uploaded";

export interface VideoMetadata {
  id: string;
  title: string;
  source: VideoSource;
  filePath: string;
  youtubeUrl: string | null;
  duration: number | null;
  thumbnailPath: string | null;
  status: ProcessingStatus;
  errorMessage: string | null;
  createdAt: string;
  completedAt: string | null;
}

export interface VideoLibraryResponse {
  videos: VideoMetadata[];
  processingCount: number;
  totalCount: number;
}

export interface VideosByGroup {
  name: string;
  videos: VideoMetadata[];
}

export interface VideoGroupsResponse {
  groups: VideosByGroup[];
}

export interface AddVideoResponse {
  videoId: string;
  title: string;
  status: ProcessingStatus;
}

export interface AddVideosResponse {
  added: AddVideoResponse[];
  errors: Array<{ filename: string; error: string }>;
}

export interface ProcessingStatusResponse {
  queueLength: number;
  processing: string[];
}

export interface VideoDetailResponse {
  video: VideoMetadata;
  transcriptText: string | null;
  segmentCount: number;
}

export interface TranscriptSegment {
  segmentId: string;
  startTime: number;
  endTime: number;
  text: string;
}

export interface VideoTranscriptResponse {
  videoId: string;
  videoTitle: string;
  segments: TranscriptSegment[];
}
