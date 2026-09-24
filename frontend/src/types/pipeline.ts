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
  abstract_es: string | null;
  abstract_en: string | null;
  abstract_es_word_count: number | null;
  abstract_en_word_count: number | null;
  abstract_word_limit: number;
  ai_suggestions: string[];
  suggested_abstract_es: string | null;
  suggested_abstract_en: string | null;
  html_url: string | null;
  source_preview_url: string | null;
  epub_url: string | null;
  delivery_dir_path: string | null;
  delivery_url: string | null;
  delivery_archive_url: string | null;
}

export interface AbstractReviewPayload {
  abstract_es?: string;
  abstract_en?: string;
}

export interface PreAnalysisResult {
  file_name: string;
  file_size_bytes: number;
  article_title: string | null;
  doi: string | null;
  journal: string | null;
  abstract_es_word_count: number;
  abstract_en_word_count: number;
  abstract_word_limit: number;
  figures_count: number;
  tables_count: number;
  references_count: number;
  estimated_seconds: number;
  issues: string[];
  suggestions: string[];
  suggested_abstract_es: string | null;
  suggested_abstract_en: string | null;
}
