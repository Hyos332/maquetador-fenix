import type {
  AbstractReviewPayload,
  CreateJobResponse,
  DeliveryExportResponse,
  JobStatusResponse,
} from "../types/pipeline";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : window.location.origin);

export function resolveApiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}

export async function uploadArticleZip(file: File): Promise<CreateJobResponse> {
  const data = new FormData();
  data.append("file", file);

  const response = await fetch(resolveApiUrl("/api/jobs"), {
    method: "POST",
    body: data,
  });

  if (!response.ok) {
    throw new Error(await readApiError(response));
  }

  return response.json();
}

export async function getJob(jobId: string): Promise<JobStatusResponse> {
  const response = await fetch(resolveApiUrl(`/api/jobs/${jobId}`));
  if (!response.ok) {
    throw new Error(await readApiError(response));
  }
  return response.json();
}

export async function updateAbstracts(jobId: string, payload: AbstractReviewPayload): Promise<CreateJobResponse> {
  const response = await fetch(resolveApiUrl(`/api/jobs/${jobId}/abstracts`), {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await readApiError(response));
  }

  return response.json();
}

export async function exportDeliveryFolder(jobId: string): Promise<DeliveryExportResponse> {
  const response = await fetch(resolveApiUrl(`/api/jobs/${jobId}/delivery/export-folder`), {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(await readApiError(response));
  }

  return response.json();
}

async function readApiError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    return payload.detail ?? "Error de API";
  } catch {
    return "Error de API";
  }
}
