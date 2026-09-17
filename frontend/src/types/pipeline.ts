export type PipelineStatus =
  | "PENDING"
  | "ANALYZING"
  | "METADATA_EXTRACTED"
  | "AUTOMATING_MLS"
  | "HTML_DOWNLOADED"
  | "POST_PROCESSING"
  | "BUILDING_EPUB"
  | "VALIDATING"
  | "NEEDS_REVIEW"
  | "COMPLETED"
  | "FAILED";

export interface CreateJobResponse {
  job_id: string;
  status: PipelineStatus;
  message: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: PipelineStatus;
  message: string;
  warnings: string[];
  error: string | null;
  article_title: string | null;
  doi: string | null;
  references_count: number | null;
  figures_count: number | null;
  html_url: string | null;
  epub_url: string | null;
  delivery_url: string | null;
}
