import { useEffect, useState } from "react";
import type { JobStatusResponse } from "../types/pipeline";

interface JobHistoryItem {
  jobId: string;
  fileName: string;
  articleTitle?: string;
  status: string;
  timestamp: number;
  completedAt?: number;
}

const HISTORY_KEY = "maquetador-job-history";
const MAX_HISTORY = 10;

export function useJobHistory() {
  const [history, setHistory] = useState<JobHistoryItem[]>(() => {
    try {
      const stored = localStorage.getItem(HISTORY_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    } catch (error) {
      console.error("Failed to save history:", error);
    }
  }, [history]);

  const addJob = (jobId: string, fileName: string) => {
    setHistory((prev) => {
      const filtered = prev.filter((item) => item.jobId !== jobId);
      const newItem: JobHistoryItem = {
        jobId,
        fileName,
        status: "PENDING",
        timestamp: Date.now(),
      };
      return [newItem, ...filtered].slice(0, MAX_HISTORY);
    });
  };

  const updateJob = (jobId: string, job: JobStatusResponse) => {
    setHistory((prev) =>
      prev.map((item) =>
        item.jobId === jobId
          ? {
              ...item,
              articleTitle: job.article_title || item.articleTitle,
              status: job.status,
              completedAt:
                job.status === "COMPLETED" || job.status === "FAILED" || job.status === "NEEDS_REVIEW"
                  ? Date.now()
                  : item.completedAt,
            }
          : item
      )
    );
  };

  const clearHistory = () => {
    setHistory([]);
  };

  const removeJob = (jobId: string) => {
    setHistory((prev) => prev.filter((item) => item.jobId !== jobId));
  };

  return {
    history,
    addJob,
    updateJob,
    clearHistory,
    removeJob,
  };
}
