import type { HealthResponse } from '../types/health'
import type { AnalysisSource, IngestionResult } from '../types/analysis'

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
    }),
  })
}

export async function createFileAnalysis(
  source: Exclude<AnalysisSource, 'app_store'>,
  file: File,
  analysisGoal: string,
): Promise<IngestionResult> {
  const formData = new FormData()
  formData.append('file', file)
  if (analysisGoal.trim()) {
    formData.append('analysis_goal', analysisGoal.trim())
  }

  return requestIngestion(`${apiBaseUrl}/api/analysis/import/${source}`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
    body: formData,
  })
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
