import { useTranslation } from 'react-i18next'

import { apiBaseUrl } from '../api/client'
import type { ConnectionState } from '../types/health'

interface BackendStatusProps {
  connection: ConnectionState
}

const visualState = {
  checking: {
    dot: 'bg-[#f2a93b]',
    panel: 'border-[#eadfca] bg-[#fffaf0]',
  },
  connected: {
    dot: 'bg-[#16a36a]',
    panel: 'border-[#cbe8dc] bg-[#f0fbf6]',
  },
  failed: {
    dot: 'bg-[#dc4c4c]',
    panel: 'border-[#efd2d2] bg-[#fff5f5]',
  },
} as const

export function BackendStatus({ connection }: BackendStatusProps) {
  const { t } = useTranslation()
  const state = visualState[connection.status]

  return (
    <section
      aria-live="polite"
      aria-busy={connection.status === 'checking'}
      className={`rounded-xl border p-4 ${state.panel}`}
    >
      <div className="flex items-start gap-3">
        <span className="relative mt-1 flex size-2.5 shrink-0" aria-hidden="true">
          {connection.status === 'checking' ? (
            <span className={`absolute inline-flex size-full animate-ping rounded-full opacity-50 ${state.dot}`} />
          ) : null}
          <span className={`relative inline-flex size-2.5 rounded-full ${state.dot}`} />
        </span>

        <div className="min-w-0">
          <p className="text-sm font-semibold tracking-[-0.01em] text-[#17304d]">
            {t(`connection.${connection.status}.title`)}
          </p>
          {connection.status === 'checking' ? (
            <p className="mt-1 text-xs leading-5 text-[#607187]">
              {t('connection.checking.description', { apiBaseUrl })}
            </p>
          ) : null}
          {connection.status === 'connected' ? (
            <p className="mt-1 text-xs leading-5 text-[#526a63]">
              {t('connection.connected.description', { service: connection.health.service })}
            </p>
          ) : null}
          {connection.status === 'failed' ? (
            <p className="mt-1 text-xs leading-5 text-[#805b5b]">
              {t('connection.failed.description', { apiBaseUrl })}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  )
}
