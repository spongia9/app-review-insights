export type AnalysisSource = 'app_store' | 'csv' | 'json'
export type AnalysisOutputLanguage = 'FOLLOW_UI' | 'zh-CN' | 'en-US'

export interface AnalysisRun {
  id: string
  source_type: AnalysisSource
  app_id: string | null
  analysis_goal: string | null
  output_language: AnalysisOutputLanguage
  resolved_output_language: Exclude<AnalysisOutputLanguage, 'FOLLOW_UI'>
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'WARNING' | 'FAILED'
  current_stage: string
  last_successful_stage: string | null
  progress: number
  warnings: string[]
  errors: string[]
  error_code: string | null
  revisions: string[]
  model_provider: string | null
  model_name: string | null
  total_review_count: number
  analyzed_review_count: number
  sampling_strategy: string | null
  batch_count: number
  batch_size: number
}

export interface Review {
  id: string
  analysis_run_id: string
  source: string
  source_review_id: string | null
  app_id: string | null
  author: string | null
  rating: number | null
  title: string | null
  text: string
  version: string | null
  language: string | null
  created_at: string | null
  storefront: string | null
  raw_data: Record<string, unknown> | null
}

export interface ProviderMetadata {
  analysis_run_id: string
  source: string
  storefront: string | null
  collection_time: string
  source_limitations: string[]
  is_live_collection: boolean
  storefront_verified: boolean
}

export interface CleaningStatistics {
  analysis_run_id: string
  raw_review_count: number
  clean_review_count: number
  duplicate_count: number
  invalid_count: number
  empty_count: number
  retention_rate: number
}

export interface RejectedReview {
  row_number: number
  code: string
  message: string
}

export interface IngestionResult {
  analysis_run_id: string
  run: AnalysisRun
  provider: ProviderMetadata
  statistics: CleaningStatistics | null
  reviews: Review[]
  rejected_rows: RejectedReview[]
}

export interface TopicCandidate {
  id: string
  analysis_run_id: string
  name: string
  summary: string
  review_ids: string[]
  batch_id: string
}

export interface FindingCandidate {
  id: string
  analysis_run_id: string
  topic: string
  title: string
  problem: string
  summary: string
  supporting_review_ids: string[]
  source_batch_ids: string[]
  candidate_status: 'UNVALIDATED_CANDIDATE'
}

export interface SemanticAnalysisSummary {
  analysis_run_id: string
  total_review_count: number
  analyzed_review_count: number
  batch_count: number
  batch_size: number
  consolidation_group_size: number | null
  model_max_output_tokens: number | null
  sampling_strategy: string
  model_provider: string
  model_name: string
  analysis_goal: string | null
  output_language: AnalysisOutputLanguage
  resolved_output_language: Exclude<AnalysisOutputLanguage, 'FOLLOW_UI'>
  topic_count: number
  finding_candidate_count: number
  analysis_time: string | null
}

export interface AnalysisRunView {
  analysis_run_id: string
  run: AnalysisRun
  provider: ProviderMetadata
  statistics: CleaningStatistics | null
  semantic_analysis: SemanticAnalysisSummary | null
}

export interface TopicsView {
  analysis_run_id: string
  topics: TopicCandidate[]
}

export interface FindingCandidatesView {
  analysis_run_id: string
  finding_candidates: FindingCandidate[]
}
