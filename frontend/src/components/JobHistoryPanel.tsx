import { Clock, FileText, CheckCircle, XCircle, AlertTriangle, Trash2 } from "lucide-react";
import { formatDistanceToNow } from "../utils/dateUtils";

interface JobHistoryItem {
  jobId: string;
  fileName: string;
  articleTitle?: string;
  status: string;
  timestamp: number;
  completedAt?: number;
}

interface JobHistoryPanelProps {
  history: JobHistoryItem[];
  onSelectJob: (jobId: string) => void;
  onRemoveJob: (jobId: string) => void;
  onClearHistory: () => void;
  currentJobId?: string | null;
}

export function JobHistoryPanel({
  history,
  onSelectJob,
  onRemoveJob,
  onClearHistory,
  currentJobId,
}: JobHistoryPanelProps) {
  if (history.length === 0) {
    return (
      <section className="history-panel history-panel--empty">
        <div className="history-panel__empty-state">
          <Clock size={48} strokeWidth={1.5} />
          <p>No hay trabajos recientes</p>
          <span>Los trabajos procesados aparecerán aquí</span>
        </div>
      </section>
    );
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "COMPLETED":
        return <CheckCircle size={16} className="status-icon status-icon--success" />;
      case "FAILED":
        return <XCircle size={16} className="status-icon status-icon--error" />;
      case "NEEDS_REVIEW":
        return <AlertTriangle size={16} className="status-icon status-icon--warning" />;
      default:
        return <Clock size={16} className="status-icon status-icon--pending" />;
    }
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      PENDING: "Pendiente",
      ANALYZING: "Analizando",
      EXTRACTING: "Extrayendo",
      GENERATING: "Generando",
      VALIDATING: "Validando",
      COMPLETED: "Completado",
      FAILED: "Fallido",
      NEEDS_REVIEW: "Requiere revisión",
    };
    return labels[status] || status;
  };

  return (
    <section className="history-panel">
      <div className="history-panel__header">
        <h3>Trabajos recientes</h3>
        {history.length > 0 && (
          <button
            type="button"
            className="button button--ghost button--sm"
            onClick={onClearHistory}
            title="Limpiar historial"
          >
            <Trash2 size={14} />
            Limpiar
          </button>
        )}
      </div>
      <ul className="history-list">
        {history.map((item) => (
          <li
            key={item.jobId}
            className={`history-item ${item.jobId === currentJobId ? "history-item--active" : ""}`}
          >
            <button
              type="button"
              className="history-item__button"
              onClick={() => onSelectJob(item.jobId)}
            >
              <div className="history-item__icon">
                <FileText size={18} />
              </div>
              <div className="history-item__content">
                <div className="history-item__title">
                  {item.articleTitle || item.fileName}
                </div>
                <div className="history-item__meta">
                  <span className="history-item__status">
                    {getStatusIcon(item.status)}
                    {getStatusLabel(item.status)}
                  </span>
                  <span className="history-item__time">
                    {formatDistanceToNow(item.completedAt || item.timestamp)}
                  </span>
                </div>
              </div>
            </button>
            <button
              type="button"
              className="history-item__remove"
              onClick={(e) => {
                e.stopPropagation();
                onRemoveJob(item.jobId);
              }}
              aria-label="Eliminar del historial"
            >
              <Trash2 size={14} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
