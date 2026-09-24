import { useEffect, useMemo, useState, useRef } from "react";
import { Dropzone } from "./components/Dropzone";
import { ProgressList } from "./components/ProgressList";
import { ResultPanel } from "./components/ResultPanel";
import { JobHistoryPanel } from "./components/JobHistoryPanel";
import { ToastContainer } from "./components/Toast";
import { UploadProgressBar } from "./hooks/useFileUpload";
import { useJobHistory } from "./hooks/useJobHistory";
import { useToast } from "./hooks/useToast";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { useFileUpload } from "./hooks/useFileUpload";
import { getJob, resolveApiUrl } from "./services/api";
import type { CreateJobResponse, JobStatusResponse, PipelineStatus } from "./types/pipeline";
import "./styles.css";

const terminalStatuses: PipelineStatus[] = ["COMPLETED", "FAILED", "NEEDS_REVIEW"];

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [status, setStatus] = useState<PipelineStatus>("PENDING");
  const [message, setMessage] = useState("Esperando documento.");
  const [error, setError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  
  const pollingIntervalRef = useRef<number>(1400);
  const consecutiveErrorsRef = useRef<number>(0);

  const { history, addJob, updateJob, clearHistory, removeJob } = useJobHistory();
  const { toasts, hideToast, success, error: errorToast } = useToast();
  const { uploadFile, cancelUpload, progress, isUploading } = useFileUpload();

  const busy = useMemo(() => {
    return Boolean(jobId && !terminalStatuses.includes(status)) || isUploading;
  }, [jobId, status, isUploading]);

  useEffect(() => {
    if (!jobId || terminalStatuses.includes(status)) return;

    pollingIntervalRef.current = 1400;
    consecutiveErrorsRef.current = 0;

    const scheduleNextPoll = () => {
      const timer = window.setTimeout(async () => {
        try {
          const nextJob = await getJob(jobId);
          setJob(nextJob);
          setStatus(nextJob.status);
          setMessage(nextJob.message);
          setError(nextJob.error);
          
          updateJob(jobId, nextJob);
          
          consecutiveErrorsRef.current = 0;
          pollingIntervalRef.current = 1400;
          
          if (terminalStatuses.includes(nextJob.status)) {
            const statusMessages = {
              COMPLETED: "Artículo procesado exitosamente",
              FAILED: "El procesamiento falló",
              NEEDS_REVIEW: "El artículo requiere revisión",
            };
            success(statusMessages[nextJob.status as keyof typeof statusMessages] || "Proceso finalizado");
            
            if ("Notification" in window && Notification.permission === "granted") {
              new Notification("Maquetador MLS", {
                body: statusMessages[nextJob.status as keyof typeof statusMessages],
                icon: "/favicon.ico",
              });
            }
          } else {
            scheduleNextPoll();
          }
        } catch (pollError) {
          consecutiveErrorsRef.current += 1;
          
          if (consecutiveErrorsRef.current >= 5) {
            setError("No se puede conectar con el servidor. Intenta recargar la página.");
            errorToast("Error de conexión con el servidor");
            return;
          }
          
          pollingIntervalRef.current = Math.min(pollingIntervalRef.current * 1.5, 10000);
          
          if (!terminalStatuses.includes(status)) {
            scheduleNextPoll();
          }
        }
      }, pollingIntervalRef.current);

      return timer;
    };

    const timer = scheduleNextPoll();

    return () => {
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [jobId, status, updateJob, success, errorToast]);

  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  useKeyboardShortcuts([
    {
      key: "Enter",
      handler: () => {
        if (file && !busy) {
          startJob();
        }
      },
    },
    {
      key: "h",
      ctrl: true,
      handler: () => {
        setShowHistory((prev) => !prev);
      },
    },
    {
      key: "Escape",
      handler: () => {
        setShowHistory(false);
      },
    },
  ], true);

  async function startJob() {
    if (!file) return;
    setError(null);
    setStatus("PENDING");
    setMessage("Subiendo documento.");
    setJob(null);

    try {
      const response = await uploadFile(resolveApiUrl("/api/jobs"), file);
      
      if (!response.ok) {
        throw new Error("Error al subir el archivo");
      }

      const created: CreateJobResponse = await response.json();
      setJobId(created.job_id);
      setStatus(created.status);
      setMessage(created.message);
      
      addJob(created.job_id, file.name);
      success("Archivo subido correctamente");
    } catch (uploadError) {
      const errorMessage = uploadError instanceof Error ? uploadError.message : "No se pudo subir el archivo.";
      setError(errorMessage);
      setStatus("FAILED");
      errorToast(errorMessage);
    }
  }

  async function loadJobFromHistory(selectedJobId: string) {
    try {
      const existingJob = await getJob(selectedJobId);
      setJobId(selectedJobId);
      setJob(existingJob);
      setStatus(existingJob.status);
      setMessage(existingJob.message);
      setError(existingJob.error);
      setShowHistory(false);
      success("Trabajo cargado desde el historial");
    } catch (err) {
      errorToast("No se pudo cargar el trabajo");
    }
  }

  function handleReviewStarted(updated: CreateJobResponse) {
    setError(null);
    setStatus(updated.status);
    setMessage(updated.message);
    setJob((current) =>
      current
        ? {
            ...current,
            status: updated.status,
            message: updated.message,
            warnings: [],
          }
        : current,
    );
  }

  return (
    <main className="app-shell">
      <section className="workspace">
        <div className="left-rail">
          <Dropzone file={file} disabled={busy} onFileSelected={setFile} onSubmit={startJob} />
          
          {isUploading && progress && (
            <UploadProgressBar progress={progress} onCancel={cancelUpload} />
          )}
          
          <ProgressList currentStatus={status} />
          
          <section className="message-panel">
            <h2>Estado actual</h2>
            <p>{error ?? message}</p>
          </section>

          {showHistory && (
            <JobHistoryPanel
              history={history}
              onSelectJob={loadJobFromHistory}
              onRemoveJob={removeJob}
              onClearHistory={clearHistory}
              currentJobId={jobId}
            />
          )}

          {!showHistory && history.length > 0 && (
            <button
              type="button"
              className="button button--secondary button--block"
              onClick={() => setShowHistory(true)}
            >
              Ver historial ({history.length})
            </button>
          )}
        </div>
        <ResultPanel job={job} onReviewStarted={handleReviewStarted} />
      </section>
      
      <ToastContainer toasts={toasts} onClose={hideToast} />
      
      <div className="keyboard-hint">
        <kbd>Ctrl</kbd> + <kbd>H</kbd> Historial • <kbd>Enter</kbd> Maquetar
      </div>
    </main>
  );
}
