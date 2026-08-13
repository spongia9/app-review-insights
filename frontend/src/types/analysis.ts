export type AnalysisSource = 'app_store' | 'csv' | 'json'

export interface AnalysisRun {
  id: string
  source_type: AnalysisSource
  app_id: string | null
  analysis_goal: string | null
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'WARNING' | 'FAILED'
  current_stage: string
  last_successful_stage: string | null
  progress: number
  warnings: string[]
  errors: string[]
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
