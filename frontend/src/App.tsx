import { useEffect, useMemo, useState } from "react";
import { Dropzone } from "./components/Dropzone";
import { ProgressList } from "./components/ProgressList";
import { ResultPanel } from "./components/ResultPanel";
import { getJob, uploadArticleZip } from "./services/api";
import type { JobStatusResponse, PipelineStatus } from "./types/pipeline";
import "./styles.css";

const terminalStatuses: PipelineStatus[] = ["COMPLETED", "FAILED", "NEEDS_REVIEW"];

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [status, setStatus] = useState<PipelineStatus>("PENDING");
  const [message, setMessage] = useState("Esperando ZIP.");
  const [error, setError] = useState<string | null>(null);

  const busy = useMemo(() => {
    return Boolean(jobId && !terminalStatuses.includes(status));
  }, [jobId, status]);

  useEffect(() => {
    if (!jobId || terminalStatuses.includes(status)) return;

    const timer = window.setInterval(async () => {
      try {
        const nextJob = await getJob(jobId);
        setJob(nextJob);
        setStatus(nextJob.status);
        setMessage(nextJob.message);
        setError(nextJob.error);
      } catch (pollError) {
        setError(pollError instanceof Error ? pollError.message : "No se pudo consultar el trabajo.");
      }
    }, 1400);

    return () => window.clearInterval(timer);
  }, [jobId, status]);

  async function startJob() {
    if (!file) return;
    setError(null);
    setStatus("PENDING");
    setMessage("Subiendo ZIP.");
    setJob(null);

    try {
      const created = await uploadArticleZip(file);
      setJobId(created.job_id);
      setStatus(created.status);
      setMessage(created.message);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "No se pudo subir el ZIP.");
      setStatus("FAILED");
    }
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
        <ResultPanel job={job} />
      </section>
    </main>
  );
}
