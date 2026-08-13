import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { getHealth } from '../api/client'
import { BackendStatus } from '../components/BackendStatus'
import { IngestionResults } from '../components/IngestionResults'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { NewAnalysisForm } from '../components/NewAnalysisForm'
import type { IngestionResult } from '../types/analysis'
import type { ConnectionState } from '../types/health'

export function HomePage() {
  const { t } = useTranslation()
  const [connection, setConnection] = useState<ConnectionState>({ status: 'checking' })
  const [result, setResult] = useState<IngestionResult | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal)
      .then((health) => setConnection({ status: 'connected', health }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setConnection({ status: 'failed' })
        }
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="min-h-screen bg-[#f4f8fc] px-4 py-5 text-[#132a46] sm:px-7 sm:py-7 lg:px-10">
      <div className="mx-auto max-w-[1280px] overflow-hidden rounded-2xl bg-white shadow-[0_8px_30px_rgba(45,81,122,0.11)]">
        <header className="flex items-center justify-between border-b border-[#dce7f1] px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-full bg-[#175bd8] font-mono text-xs font-bold text-white">AR</span>
            <div>
              <p className="text-sm font-semibold tracking-[-0.01em]">{t('brand.name')}</p>
              <p className="text-[0.68rem] text-[#728499]">{t('brand.subtitle')}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <LanguageSwitcher />
            <span className="hidden rounded-full border border-[#d7e3ee] px-3 py-1 font-mono text-[0.68rem] text-[#65778d] sm:inline-flex">
              {t('header.phase2')}
            </span>
          </div>
        </header>

        <div className="grid gap-7 px-5 py-7 sm:px-8 lg:grid-cols-[minmax(0,1fr)_360px] lg:px-10 lg:py-10">
          <section>
            <div className="mb-7 max-w-2xl">
              <h1 className="text-3xl font-semibold tracking-[-0.035em] text-[#102943] sm:text-4xl">
                {t('analysis.page.title')}
              </h1>
              <p className="mt-3 text-sm leading-6 text-[#61748a] sm:text-base sm:leading-7">
                {t('analysis.page.description')}
              </p>
            </div>
            <NewAnalysisForm onComplete={setResult} />
          </section>

          <aside className="lg:pt-[5.9rem]">
            <div className="mb-3 flex items-end justify-between px-1">
              <div>
                <p className="font-mono text-[0.68rem] uppercase tracking-[0.14em] text-[#7b8ca0]">{t('system.eyebrow')}</p>
                <h2 className="mt-1 text-lg font-semibold tracking-[-0.025em]">{t('system.backendStatus')}</h2>
              </div>
              <span className="font-mono text-[0.62rem] text-[#8495a8]">{t('system.healthEndpoint')}</span>
            </div>
            <BackendStatus connection={connection} />
            <div className="mt-5 rounded-2xl bg-[#eef4fa] p-5 text-sm leading-6 text-[#536b83]">
              <p className="font-semibold text-[#294765]">{t('analysis.page.scopeTitle')}</p>
              <p className="mt-1">{t('analysis.page.scopeDescription')}</p>
            </div>
          </aside>
        </div>

        {result ? (
          <div className="border-t border-[#dce7f1] px-5 py-8 sm:px-8 lg:px-10">
            <IngestionResults result={result} />
          </div>
        ) : null}

        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-[#dce7f1] px-5 py-4 font-mono text-[0.65rem] uppercase tracking-[0.12em] text-[#788a9e] sm:px-8">
          <span>{t('system.technology')}</span>
          <span>{t('analysis.page.footer')}</span>
        </footer>
      </div>
    </main>
  )
}
