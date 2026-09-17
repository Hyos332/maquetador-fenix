import { Download, ExternalLink, FileText, FolderOpen, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { resolveApiUrl, updateAbstracts } from "../services/api";
import type { CreateJobResponse, JobStatusResponse } from "../types/pipeline";

interface ResultPanelProps {
  job: JobStatusResponse | null;
  onReviewStarted: (job: CreateJobResponse) => void;
}

export function ResultPanel({ job, onReviewStarted }: ResultPanelProps) {
  const [abstractEs, setAbstractEs] = useState("");
  const [abstractEn, setAbstractEn] = useState("");
  const [savingReview, setSavingReview] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  useEffect(() => {
    setAbstractEs(job?.abstract_es ?? "");
    setAbstractEn(job?.abstract_en ?? "");
    setReviewError(null);
  }, [job?.job_id, job?.abstract_es, job?.abstract_en]);

  if (!job) {
    return (
      <section className="result-panel result-panel--empty">
        <FileText size={24} />
        <p>La vista previa aparecerá cuando el HTML esté generado.</p>
      </section>
    );
  }

  const htmlUrl = job.html_url ? resolveApiUrl(job.html_url) : null;
  const epubUrl = job.epub_url ? resolveApiUrl(job.epub_url) : null;
  const deliveryUrl = job.delivery_url ? resolveApiUrl(job.delivery_url) : null;
  const jobId = job.job_id;
  const abstractReview = getAbstractReviewState(job, abstractEs, abstractEn);

  async function submitAbstractReview() {
    if (!abstractReview.shouldShow || abstractReview.hasOverLimit) return;

    setSavingReview(true);
    setReviewError(null);
    try {
      const payload = {
        ...(abstractReview.showEs ? { abstract_es: abstractEs } : {}),
        ...(abstractReview.showEn ? { abstract_en: abstractEn } : {}),
      };
      const updated = await updateAbstracts(jobId, payload);
      onReviewStarted(updated);
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : "No se pudo enviar la revisión.");
    } finally {
      setSavingReview(false);
    }
  }

  return (
    <section className="result-panel">
      <div className="result-panel__header">
        <div>
          <h2>{job.article_title ?? "Artículo en proceso"}</h2>
          <p>{job.doi ?? "DOI pendiente"}</p>
        </div>
        <span className={`status-pill status-pill--${job.status.toLowerCase()}`}>{labelForStatus(job.status)}</span>
      </div>

      <dl className="metrics">
        <div>
          <dt>Referencias</dt>
          <dd>{job.references_count ?? "-"}</dd>
        </div>
        <div>
          <dt>Figuras</dt>
          <dd>{job.figures_count ?? "-"}</dd>
        </div>
      </dl>

      {job.warnings.length ? (
        <div className="warnings">
          <h3>Revisión necesaria</h3>
          {job.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      ) : null}

      {abstractReview.shouldShow ? (
        <div className="abstract-review">
          <div className="abstract-review__header">
            <h3>Resumen fuera de límite</h3>
            <span>
              Máximo {job.abstract_word_limit} palabras
            </span>
          </div>

          {abstractReview.showEs ? (
            <label className="abstract-field">
              <span>
                Resumen
                <strong className={abstractReview.esCount > job.abstract_word_limit ? "over-limit" : ""}>
                  {abstractReview.esCount}/{job.abstract_word_limit}
                </strong>
              </span>
              <textarea value={abstractEs} onChange={(event) => setAbstractEs(event.target.value)} />
            </label>
          ) : null}

          {abstractReview.showEn ? (
            <label className="abstract-field">
              <span>
                Abstract
                <strong className={abstractReview.enCount > job.abstract_word_limit ? "over-limit" : ""}>
                  {abstractReview.enCount}/{job.abstract_word_limit}
                </strong>
              </span>
              <textarea value={abstractEn} onChange={(event) => setAbstractEn(event.target.value)} />
            </label>
          ) : null}

          {reviewError ? <p className="review-error">{reviewError}</p> : null}

          <button
            className="button button--primary"
            type="button"
            disabled={savingReview || abstractReview.hasOverLimit}
            onClick={submitAbstractReview}
          >
            <Send size={17} />
            {savingReview ? "Enviando" : "Aplicar y regenerar"}
          </button>
        </div>
      ) : null}

      {job.delivery_dir_path ? (
        <div className="folder-output">
          <FolderOpen size={20} />
          <div>
            <h3>Carpeta organizada</h3>
            <code>{job.delivery_dir_path}</code>
          </div>
        </div>
      ) : null}

      <div className="result-actions">
        {htmlUrl ? (
          <a className="button button--secondary" href={htmlUrl} target="_blank" rel="noreferrer">
            <ExternalLink size={17} />
            Ver HTML
          </a>
        ) : null}
        {epubUrl ? (
          <a className="button button--primary" href={epubUrl}>
            <Download size={17} />
            Descargar EPUB
          </a>
        ) : null}
        {deliveryUrl ? (
          <a className="button button--primary" href={deliveryUrl}>
            <Download size={17} />
            Descargar ZIP opcional
          </a>
        ) : null}
      </div>

      {htmlUrl ? <iframe className="preview" title="Vista previa HTML" src={htmlUrl} /> : null}
    </section>
  );
}

function getAbstractReviewState(job: JobStatusResponse, abstractEs: string, abstractEn: string) {
  const limit = job.abstract_word_limit;
  const esWasOver = (job.abstract_es_word_count ?? 0) > limit || hasAbstractWarning(job.warnings, "Resumen");
  const enWasOver = (job.abstract_en_word_count ?? 0) > limit || hasAbstractWarning(job.warnings, "Abstract");
  const esCount = countWords(abstractEs);
  const enCount = countWords(abstractEn);
  const showEs = Boolean(job.abstract_es) && esWasOver;
  const showEn = Boolean(job.abstract_en) && enWasOver;

  return {
    shouldShow: job.status === "NEEDS_REVIEW" && (showEs || showEn),
    showEs,
    showEn,
    esCount,
    enCount,
    hasOverLimit: (showEs && esCount > limit) || (showEn && enCount > limit),
  };
}

function hasAbstractWarning(warnings: string[], label: "Resumen" | "Abstract") {
  return warnings.some((warning) => warning.startsWith(`${label} has`) && warning.includes("250"));
}

function countWords(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return 0;
  return trimmed.split(/\s+/).length;
}

function labelForStatus(status: string) {
  const labels: Record<string, string> = {
    PENDING: "Pendiente",
    ANALYZING: "Analizando",
    METADATA_EXTRACTED: "Metadatos",
    AUTOMATING_MLS: "Maquetador MLS",
    POST_PROCESSING: "HTML",
    BUILDING_EPUB: "EPUB",
    VALIDATING: "Validando",
    NEEDS_REVIEW: "Revisión",
    COMPLETED: "Completado",
    FAILED: "Falló",
  };
  return labels[status] ?? status;
}
