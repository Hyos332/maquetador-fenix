import { useEffect, useMemo, useState, useRef } from "react";
import { Dropzone } from "./components/Dropzone";
import { ProgressList } from "./components/ProgressList";
import { ResultPanel } from "./components/ResultPanel";
import { getJob, uploadArticleZip } from "./services/api";
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
  
  const pollingIntervalRef = useRef<number>(1400);
  const consecutiveErrorsRef = useRef<number>(0);

  const busy = useMemo(() => {
    return Boolean(jobId && !terminalStatuses.includes(status));
  }, [jobId, status]);

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
          
          consecutiveErrorsRef.current = 0;
          pollingIntervalRef.current = 1400;
          
          if (!terminalStatuses.includes(nextJob.status)) {
            scheduleNextPoll();
          }
        } catch (pollError) {
          consecutiveErrorsRef.current += 1;
          
          if (consecutiveErrorsRef.current >= 5) {
            setError("No se puede conectar con el servidor. Intenta recargar la página.");
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
  }, [jobId, status]);

  async function startJob() {
    if (!file) return;
    setError(null);
    setStatus("PENDING");
    setMessage("Subiendo documento.");
    setJob(null);

    try {
      const created = await uploadArticleZip(file);
      setJobId(created.job_id);
      setStatus(created.status);
      setMessage(created.message);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "No se pudo subir el archivo.");
      setStatus("FAILED");
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
          <ProgressList currentStatus={status} />
          <section className="message-panel">
            <h2>Estado actual</h2>
            <p>{error ?? message}</p>
          </section>
        </div>
        <ResultPanel job={job} onReviewStarted={handleReviewStarted} />
      </section>
    </main>
  );
}
