import { Download, FileText, FolderOpen, Send, Sparkles, X } from "lucide-react";
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
  const [compareOpen, setCompareOpen] = useState(false);

  useEffect(() => {
    setAbstractEs(job?.abstract_es ?? "");
    setAbstractEn(job?.abstract_en ?? "");
    setReviewError(null);
    setCompareOpen(false);
  }, [job?.job_id, job?.abstract_es, job?.abstract_en]);

  useEffect(() => {
    if (!compareOpen) return;

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setCompareOpen(false);
      }
    }

    document.body.classList.add("modal-open");
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.classList.remove("modal-open");
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [compareOpen]);

  if (!job) {
    return (
      <section className="result-panel result-panel--empty">
        <FileText size={24} />
        <p>La vista previa aparecerá cuando el HTML esté generado.</p>
      </section>
    );
  }

  const htmlUrl = job.html_url ? resolveApiUrl(job.html_url) : null;
  const sourcePreviewUrl = job.source_preview_url ? resolveApiUrl(job.source_preview_url) : null;
  const deliveryArchiveUrl = job.delivery_archive_url ? resolveApiUrl(job.delivery_archive_url) : null;
  const jobId = job.job_id;
  const abstractReview = getAbstractReviewState(job, abstractEs, abstractEn);
  const regularWarnings = job.warnings.filter((warning) => !warning.startsWith("AI: "));

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

      {regularWarnings.length ? (
        <div className="warnings">
          <h3>Revisión necesaria</h3>
          {regularWarnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      ) : null}

      {job.ai_suggestions.length ? (
        <div className="ai-review">
          <div className="ai-review__header">
            <Sparkles size={18} />
            <h3>Revisión IA local</h3>
          </div>
          {job.ai_suggestions.map((suggestion) => (
            <p key={suggestion}>{suggestion}</p>
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
              {job.suggested_abstract_es ? (
                <button
                  className="button button--secondary button--compact"
                  type="button"
                  onClick={() => setAbstractEs(job.suggested_abstract_es ?? "")}
                >
                  <Sparkles size={15} />
                  Usar sugerencia IA
                </button>
              ) : null}
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
              {job.suggested_abstract_en ? (
                <button
                  className="button button--secondary button--compact"
                  type="button"
                  onClick={() => setAbstractEn(job.suggested_abstract_en ?? "")}
                >
                  <Sparkles size={15} />
                  Usar sugerencia IA
                </button>
              ) : null}
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
            <h3>Carpeta guardada en tu PC</h3>
            <code>{job.delivery_dir_path}</code>
          </div>
        </div>
      ) : null}

      <div className="result-actions">
        {deliveryArchiveUrl ? (
          <a className="button button--primary" href={deliveryArchiveUrl}>
            <Download size={17} />
            Descargar carpeta completa
          </a>
        ) : null}
        {htmlUrl && sourcePreviewUrl ? (
          <button className="button button--secondary" type="button" onClick={() => setCompareOpen(true)}>
            <FileText size={17} />
            Comparar documento original
          </button>
        ) : null}
      </div>

      {htmlUrl ? (
        <section className="preview-pane preview-pane--single">
          <h3>HTML generado</h3>
          <iframe className="preview" title="Vista previa HTML generado" src={htmlUrl} />
        </section>
      ) : null}

      {compareOpen && htmlUrl && sourcePreviewUrl ? (
        <div className="compare-modal" role="dialog" aria-modal="true" aria-labelledby="compare-title">
          <div className="compare-modal__backdrop" onClick={() => setCompareOpen(false)} />
          <div className="compare-modal__panel">
            <header className="compare-modal__header">
              <div>
                <h2 id="compare-title">Comparar documento original</h2>
                <p>{job.article_title ?? "Artículo maquetado"}</p>
              </div>
              <button
                className="button button--secondary button--icon"
                type="button"
                aria-label="Cerrar comparación"
                onClick={() => setCompareOpen(false)}
              >
                <X size={18} />
              </button>
            </header>
            <div className="compare-modal__grid">
              <section className="preview-pane">
                <h3>HTML generado</h3>
                <iframe className="preview preview--modal" title="Vista previa HTML generado" src={htmlUrl} />
              </section>
              <section className="preview-pane">
                <h3>DOCX original</h3>
                <iframe className="preview preview--modal" title="Vista previa DOCX original" src={sourcePreviewUrl} />
              </section>
            </div>
          </div>
        </div>
      ) : null}
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
