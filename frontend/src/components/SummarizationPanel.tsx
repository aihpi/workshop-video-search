import React, { useState } from "react";
import { summarizeTranscript } from "../services/api";
import { LoadingIndicatorButton } from "./LoadingIndicatorButton";

interface SummarizationPanelProps {
  videoId: string;
  onError: (error: Error | null) => void;
}

const SummarizationPanel: React.FC<SummarizationPanelProps> = ({
  videoId,
  onError,
}) => {
  const [summary, setSummary] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSummarize = async () => {
    setIsLoading(true);
    setSummary(null);
    onError(null);

    try {
      const response = await summarizeTranscript(videoId);
      setSummary(response.summary);
    } catch (error) {
      console.error("Error during summarization:", error);
      onError(
        error instanceof Error ? error : new Error("Summarization failed")
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">
          📝 Transcript Summary
        </h3>
        <LoadingIndicatorButton
          isLoading={isLoading}
          buttonText="Generate Summary"
          onClick={handleSummarize}
          disabled={isLoading}
        />
      </div>

      {summary && (
        <div className="mt-4">
          <div className="bg-gray-50 rounded-md p-4 border-l-4 border-indigo-500">
            <h4 className="text-sm font-medium text-gray-900 mb-2">Summary:</h4>
            <p className="text-gray-700 leading-relaxed">{summary}</p>
          </div>
        </div>
      )}

      {!summary && !isLoading && (
        <div className="mt-4 text-center text-gray-500">
          <p>
            Click "Generate Summary" to get an AI-powered summary of the entire
            transcript.
          </p>
        </div>
      )}
    </div>
  );
};

export default SummarizationPanel;
