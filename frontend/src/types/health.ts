export interface HealthResponse {
  status: 'ok'
  service: string
}

export type ConnectionState =
  | { status: 'checking' }
  | { status: 'connected'; health: HealthResponse }
  | { status: 'failed'; message: string }
