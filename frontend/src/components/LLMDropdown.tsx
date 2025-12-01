import React, { useState, useEffect } from "react";
import { listLlms, selectLlm } from "../services/api";
import type { LlmInfo, LlmListResponse } from "../types/llms.types";

interface LLMDropdownProps {
  onError: (error: Error | null) => void;
}

const LLMDropdown: React.FC<LLMDropdownProps> = ({ onError }) => {
  const [llms, setLlms] = useState<LlmInfo[]>([]);
  const [selectedLlmId, setSelectedLlmId] = useState<string>("");
  const [activeModelId, setActiveModelId] = useState<string | null>(null);
  const [hasGpu, setHasGpu] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingModels, setIsLoadingModels] = useState(true);

  useEffect(() => {
    loadModels();
  }, []);

  const loadModels = async () => {
    try {
      setIsLoadingModels(true);
      const response: LlmListResponse = await listLlms();
      setLlms(response.models);
      setActiveModelId(response.activeModelId);
      setHasGpu(response.hasGpu);
      setSelectedLlmId(response.activeModelId || "");
      onError(null);
    } catch (error) {
      console.error("Error loading LLM models:", error);
      onError(
        error instanceof Error ? error : new Error("Failed to load LLM models")
      );
    } finally {
      setIsLoadingModels(false);
    }
  };

  const handleModelChange = async (modelId: string) => {
    if (!modelId || modelId === activeModelId) return;

    try {
      setIsLoading(true);
      setSelectedLlmId(modelId);
      const response = await selectLlm(modelId);
      if (response.success) {
        setActiveModelId(modelId);
        onError(null);
      } else {
        throw new Error("Failed to select model");
      }
    } catch (error) {
      console.error("Error selecting LLM model:", error);
      onError(
        error instanceof Error ? error : new Error("Failed to select LLM model")
      );
      // Reset to previous selection on error
      setSelectedLlmId(activeModelId || "");
    } finally {
      setIsLoading(false);
    }
  };

  const getModelStatusText = (llm: LlmInfo) => {
    if (llm.modelId === activeModelId) return "Active";
    if (llm.loaded) return "Loaded";
    return "Not Loaded";
  };

  const formatOptionText = (llm: LlmInfo) => {
    const status = getModelStatusText(llm);
    const gpuReq = llm.requiresGpu ? " (GPU)" : "";
    return `${llm.displayName}${gpuReq} - ${status}`;
  };

  if (isLoadingModels) {
    return (
      <div>
        <label
          htmlFor="llm-model"
          className="block text-sm font-medium text-gray-700"
        >
          LLM Model
        </label>
        <div className="mt-1 flex items-center">
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-indigo-600"></div>
          <span className="ml-2 text-sm text-gray-600">Loading models...</span>
        </div>
      </div>
    );
  }

  return (
    <div>
      <label
        htmlFor="llm-model"
        className="block text-sm font-medium text-gray-700"
      >
        LLM Model
        {!hasGpu && (
          <span className="ml-2 text-xs text-yellow-600">
            (No GPU - Limited models)
          </span>
        )}
      </label>
      <div className="relative">
        <select
          id="llm-model"
          value={selectedLlmId}
          onChange={(e) => handleModelChange(e.target.value)}
          disabled={isLoading}
          className={`mt-1 block w-full px-3 py-2 pr-8 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 appearance-none cursor-pointer ${
            isLoading ? "bg-gray-100 cursor-not-allowed" : "bg-white"
          } text-gray-900`}
        >
          {llms.map((llm) => {
            const isDisabled = llm.requiresGpu && !hasGpu;
            return (
              <option
                key={llm.modelId}
                value={llm.modelId}
                disabled={isDisabled}
                className={isDisabled ? "text-gray-400" : ""}
              >
                {formatOptionText(llm)}
                {isDisabled ? " (Requires GPU)" : ""}
              </option>
            );
          })}
        </select>
        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2 mt-1">
          {isLoading ? (
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-indigo-600"></div>
          ) : (
            <svg className="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </div>
      </div>
    </div>
  );
};

export default LLMDropdown;
