import { Download, ExternalLink, FileText } from "lucide-react";
import { resolveApiUrl } from "../services/api";
import type { JobStatusResponse } from "../types/pipeline";

interface ResultPanelProps {
  job: JobStatusResponse | null;
}

export function ResultPanel({ job }: ResultPanelProps) {
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
            Descargar entrega ZIP
          </a>
        ) : null}
      </div>

      {htmlUrl ? <iframe className="preview" title="Vista previa HTML" src={htmlUrl} /> : null}
    </section>
  );
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
