import type { HealthResponse } from '../types/health'

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export const apiBaseUrl = configuredBaseUrl.replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
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
