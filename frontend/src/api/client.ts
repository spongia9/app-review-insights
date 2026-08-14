import type { HealthResponse } from '../types/health'
import type {
  AnalysisOutputLanguage,
  AnalysisRunView,
  AnalysisSource,
  FindingCandidatesView,
  FindingsView,
  IngestionResult,
  TopicsView,
} from '../types/analysis'

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export const apiBaseUrl = configuredBaseUrl.replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly code = 'BACKEND_ERROR',
    readonly analysisRunId?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

interface ErrorDetail {
  code?: string
  message?: string
  analysis_run_id?: string
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  let response: Response

  try {
    response = await fetch(`${apiBaseUrl}/api/health`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new ApiError(`Unable to reach the backend at ${apiBaseUrl}.`)
  }

  if (!response.ok) {
    throw new ApiError(`Backend health check returned HTTP ${response.status}.`, response.status)
  }

  const payload: unknown = await response.json()
  if (!isHealthResponse(payload)) {
    throw new ApiError('Backend health response did not match the expected contract.')
  }

  return payload
}

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== 'object' || value === null) {
    return false
  }

  const candidate = value as Record<string, unknown>
  return candidate.status === 'ok' && typeof candidate.service === 'string'
}

export async function createAppStoreAnalysis(
  appStoreUrl: string,
  analysisGoal: string,
  outputLanguage: AnalysisOutputLanguage,
): Promise<IngestionResult> {
  return requestIngestion(`${apiBaseUrl}/api/analysis/app-store`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      app_store_url: appStoreUrl,
      analysis_goal: analysisGoal.trim() || null,
      output_language: outputLanguage,
    }),
  })
}

export async function createFileAnalysis(
  source: Exclude<AnalysisSource, 'app_store'>,
  file: File,
  analysisGoal: string,
  outputLanguage: AnalysisOutputLanguage,
): Promise<IngestionResult> {
  const formData = new FormData()
  formData.append('file', file)
  if (analysisGoal.trim()) {
    formData.append('analysis_goal', analysisGoal.trim())
  }
  formData.append('output_language', outputLanguage)

  return requestIngestion(`${apiBaseUrl}/api/analysis/import/${source}`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
    body: formData,
  })
}

export async function startSemanticAnalysis(
  analysisRunId: string,
  outputLanguage: AnalysisOutputLanguage,
  uiLanguage: string,
): Promise<AnalysisRunView> {
  return requestJson<AnalysisRunView>(`${apiBaseUrl}/api/analysis/${analysisRunId}/semantic`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ output_language: outputLanguage, ui_language: uiLanguage }),
  })
}

export async function getAnalysisRun(analysisRunId: string): Promise<AnalysisRunView> {
  return requestJson<AnalysisRunView>(`${apiBaseUrl}/api/analysis/${analysisRunId}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
}

export async function getTopics(analysisRunId: string): Promise<TopicsView> {
  return requestJson<TopicsView>(`${apiBaseUrl}/api/analysis/${analysisRunId}/topics`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
}

export async function getFindingCandidates(analysisRunId: string): Promise<FindingCandidatesView> {
  return requestJson<FindingCandidatesView>(`${apiBaseUrl}/api/analysis/${analysisRunId}/finding-candidates`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
}

export async function startEvidenceValidation(analysisRunId: string): Promise<AnalysisRunView> {
  return requestJson<AnalysisRunView>(`${apiBaseUrl}/api/analysis/${analysisRunId}/evidence`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
}

export async function getFindings(analysisRunId: string): Promise<FindingsView> {
  return requestJson<FindingsView>(`${apiBaseUrl}/api/analysis/${analysisRunId}/findings`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
}

async function requestJson<T>(url: string, init: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    throw new ApiError(`Unable to reach the backend at ${apiBaseUrl}.`)
  }
  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = extractErrorDetail(payload)
    throw new ApiError(
      detail.message ?? `Backend request returned HTTP ${response.status}.`,
      response.status,
      detail.code ?? 'BACKEND_ERROR',
      detail.analysis_run_id,
    )
  }
  return payload as T
}

async function requestIngestion(url: string, init: RequestInit): Promise<IngestionResult> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    throw new ApiError(`Unable to reach the backend at ${apiBaseUrl}.`)
  }

  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = extractErrorDetail(payload)
    throw new ApiError(
      detail.message ?? `Backend request returned HTTP ${response.status}.`,
      response.status,
      detail.code ?? 'BACKEND_ERROR',
      detail.analysis_run_id,
    )
  }
  if (!isIngestionResult(payload)) {
    throw new ApiError('Backend ingestion response did not match the expected contract.')
  }
  return payload
}

function extractErrorDetail(payload: unknown): ErrorDetail {
  if (typeof payload !== 'object' || payload === null) {
    return {}
  }
  const detail = (payload as Record<string, unknown>).detail
  if (typeof detail !== 'object' || detail === null) {
    return {}
  }
  return detail as ErrorDetail
}

function isIngestionResult(value: unknown): value is IngestionResult {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.analysis_run_id === 'string' &&
    typeof candidate.run === 'object' &&
    typeof candidate.provider === 'object' &&
    typeof candidate.statistics === 'object' &&
    Array.isArray(candidate.reviews)
  )
}
