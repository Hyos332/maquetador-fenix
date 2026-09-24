import { useState, useCallback } from "react";
import { formatFileSize } from "../utils/dateUtils";

interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
  speed: number;
  estimatedTime: number;
}

export function useFileUpload() {
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [abortController, setAbortController] = useState<AbortController | null>(null);

  const uploadFile = useCallback(
    async (url: string, file: File, extraFields?: Record<string, string>): Promise<Response> => {
      const controller = new AbortController();
      setAbortController(controller);
      setIsUploading(true);

      const startTime = Date.now();
      let lastLoaded = 0;
      let lastTime = startTime;

      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener("progress", (e) => {
          if (e.lengthComputable) {
            const now = Date.now();
            const timeDiff = (now - lastTime) / 1000;
            const loadedDiff = e.loaded - lastLoaded;
            const speed = timeDiff > 0 ? loadedDiff / timeDiff : 0;
            const remaining = e.total - e.loaded;
            const estimatedTime = speed > 0 ? remaining / speed : 0;

            setProgress({
              loaded: e.loaded,
              total: e.total,
              percentage: Math.round((e.loaded / e.total) * 100),
              speed,
              estimatedTime,
            });

            lastLoaded = e.loaded;
            lastTime = now;
          }
        });

        xhr.addEventListener("load", () => {
          setIsUploading(false);
          setProgress(null);
          setAbortController(null);

          if (xhr.status >= 200 && xhr.status < 300) {
            const response = new Response(xhr.responseText, {
              status: xhr.status,
              statusText: xhr.statusText,
              headers: new Headers(
                xhr
                  .getAllResponseHeaders()
                  .split("\r\n")
                  .filter((line) => line)
                  .map((line) => line.split(": ") as [string, string])
              ),
            });
            resolve(response);
          } else {
            reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`));
          }
        });

        xhr.addEventListener("error", () => {
          setIsUploading(false);
          setProgress(null);
          setAbortController(null);
          reject(new Error("Network error"));
        });

        xhr.addEventListener("abort", () => {
          setIsUploading(false);
          setProgress(null);
          setAbortController(null);
          reject(new Error("Upload cancelled"));
        });

        controller.signal.addEventListener("abort", () => {
          xhr.abort();
        });

        const formData = new FormData();
        formData.append("file", file);
        if (extraFields) {
          for (const [key, value] of Object.entries(extraFields)) {
            if (value) {
              formData.append(key, value);
            }
          }
        }

        xhr.open("POST", url);
        xhr.send(formData);
      });
    },
    []
  );

  const cancelUpload = useCallback(() => {
    if (abortController) {
      abortController.abort();
    }
  }, [abortController]);

  return {
    uploadFile,
    cancelUpload,
    progress,
    isUploading,
  };
}

interface UploadProgressBarProps {
  progress: UploadProgress;
  onCancel: () => void;
}

export function UploadProgressBar({ progress, onCancel }: UploadProgressBarProps) {
  const formatSpeed = (bytesPerSecond: number) => {
    return `${formatFileSize(bytesPerSecond)}/s`;
  };

  const formatTime = (seconds: number) => {
    if (seconds < 60) {
      return `${Math.ceil(seconds)}s`;
    }
    const minutes = Math.floor(seconds / 60);
    const secs = Math.ceil(seconds % 60);
    return `${minutes}m ${secs}s`;
  };

  return (
    <div className="upload-progress">
      <div className="upload-progress__header">
        <span className="upload-progress__label">Subiendo archivo...</span>
        <span className="upload-progress__percentage">{progress.percentage}%</span>
      </div>
      <div className="upload-progress__bar-container">
        <div
          className="upload-progress__bar"
          style={{ width: `${progress.percentage}%` }}
        />
      </div>
      <div className="upload-progress__footer">
        <span className="upload-progress__stats">
          {formatFileSize(progress.loaded)} / {formatFileSize(progress.total)}
          {progress.speed > 0 && (
            <>
              {" • "}
              {formatSpeed(progress.speed)}
              {" • "}
              {formatTime(progress.estimatedTime)} restantes
            </>
          )}
        </span>
        <button
          type="button"
          className="button button--ghost button--sm"
          onClick={onCancel}
        >
          Cancelar
        </button>
      </div>
    </div>
  );
}
