import React from "react";

interface LoadingIndicatorButtonProps {
  isLoading: boolean;
  buttonText: string;
  disabled?: boolean;
  onClick?: () => void;
  className?: string;
  type?: "button" | "submit" | "reset";
}

export const LoadingIndicatorButton: React.FC<LoadingIndicatorButtonProps> = ({
  isLoading,
  buttonText,
  disabled = false,
  onClick,
  className = "",
  type = "submit",
}) => {
  const baseClasses = "flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500";
  
  const stateClasses = isLoading || disabled 
    ? "bg-indigo-400 cursor-not-allowed" 
    : "bg-indigo-600 hover:bg-indigo-700";
  
  // If className is provided, it can override w-full
  const widthClass = className?.includes('w-') ? '' : 'w-full';
  
  const combinedClasses = [baseClasses, stateClasses, widthClass, className]
    .filter(Boolean)
    .join(' ');

  return (
    <div>
      <button
        type={type}
        disabled={isLoading || disabled}
        onClick={onClick}
        className={combinedClasses}
      >
        {isLoading ? (
          <>
            <svg
              className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
              xmlns="http://www.w3.org/2000/svg"
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
              ></circle>
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
            Processing...
          </>
        ) : (
          buttonText
        )}
      </button>
    </div>
  );
};
