import { Check, Circle, Loader2, TriangleAlert, X } from "lucide-react";
import type { PipelineStatus } from "../types/pipeline";

const steps: Array<{ status: PipelineStatus; label: string }> = [
  { status: "ANALYZING", label: "Analizar documentos" },
  { status: "METADATA_EXTRACTED", label: "Extraer metadatos" },
  { status: "POST_PROCESSING", label: "Generar y corregir HTML" },
  { status: "BUILDING_EPUB", label: "Crear EPUB" },
  { status: "VALIDATING", label: "Validar entrega" },
  { status: "COMPLETED", label: "Listo para entregar" },
];

const order = steps.map((step) => step.status);

interface ProgressListProps {
  currentStatus: PipelineStatus;
}

export function ProgressList({ currentStatus }: ProgressListProps) {
  const currentIndex = order.indexOf(currentStatus);

  return (
    <section className="progress-panel">
      <h2>Progreso</h2>
      <ol className="progress-list">
        {steps.map((step, index) => {
          const state = getStepState(currentStatus, currentIndex, index);
          return (
            <li key={step.status} className={`progress-item progress-item--${state}`}>
              <span className="progress-item__icon">{renderIcon(state)}</span>
              <span>{step.label}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function getStepState(status: PipelineStatus, currentIndex: number, index: number) {
  if (status === "FAILED") return index <= Math.max(currentIndex, 0) ? "failed" : "pending";
  if (status === "NEEDS_REVIEW") return index < steps.length - 1 ? "done" : "review";
  if (currentIndex === -1) return index === 0 && status !== "PENDING" ? "active" : "pending";
  if (index < currentIndex) return "done";
  if (index === currentIndex) return status === "COMPLETED" ? "done" : "active";
  return "pending";
}

function renderIcon(state: string) {
  if (state === "done") return <Check size={16} />;
  if (state === "active") return <Loader2 size={16} className="spin" />;
  if (state === "failed") return <X size={16} />;
  if (state === "review") return <TriangleAlert size={16} />;
  return <Circle size={16} />;
}
