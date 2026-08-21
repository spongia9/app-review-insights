import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { getAnalysisWorkspace, getHealth } from '../api/client'
import { BackendStatus } from '../components/BackendStatus'
import { AnalysisWorkspace } from '../components/AnalysisWorkspace'
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

  useEffect(() => {
    const analysisRunId = new URLSearchParams(window.location.search).get('run')
    if (!analysisRunId) {
      return
    }
    getAnalysisWorkspace(analysisRunId)
      .then(setResult)
      .catch(() => {
        // A missing or expired in-memory run must not prevent a new analysis.
        window.history.replaceState({}, '', window.location.pathname)
      })
  }, [])

  function handleAnalysisComplete(nextResult: IngestionResult) {
    setResult(nextResult)
    const url = new URL(window.location.href)
    url.searchParams.set('run', nextResult.analysis_run_id)
    window.history.replaceState({}, '', url)
  }

  return (
    <div className="flex min-h-dvh flex-col bg-[#f4f8fc] text-[#132a46]">
      <header className="border-b border-[#dce7f1] bg-white">
        <div className="mx-auto flex min-h-16 w-full max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-6 md:px-8 lg:px-10 xl:px-12 2xl:px-16">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-full bg-[#175bd8] font-mono text-xs font-bold text-white">AR</span>
            <div className="min-w-0">
              <p className="text-sm font-semibold tracking-[-0.01em]">{t('brand.name')}</p>
              <p className="text-[0.68rem] text-[#728499]">{t('brand.subtitle')}</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            <LanguageSwitcher />
            <span className="hidden font-mono text-[0.62rem] tracking-[0.08em] text-[#8a9aad] md:inline">
              {t('header.phase7')}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 sm:px-6 sm:py-8 md:px-8 lg:px-10 lg:py-10 xl:px-12 2xl:px-16">
        <div className="grid min-w-0 gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(17rem,20rem)] lg:gap-10 xl:gap-12">
          <section className="min-w-0">
            <div className="mb-6 max-w-2xl sm:mb-7">
              <h1 className="text-[1.75rem] font-semibold tracking-[-0.03em] text-[#102943] sm:text-[2rem] lg:text-[2.125rem]">
                {t('analysis.page.title')}
              </h1>
              <p className="mt-2.5 max-w-[68ch] text-sm leading-6 text-[#61748a] sm:text-base sm:leading-7">
                {t('analysis.page.description')}
              </p>
            </div>
            <NewAnalysisForm onComplete={handleAnalysisComplete} />
          </section>

          <aside className="min-w-0 border-t border-[#dce7f1] pt-6 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0 xl:pl-10">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <p className="font-mono text-[0.68rem] uppercase tracking-[0.14em] text-[#7b8ca0]">{t('system.eyebrow')}</p>
                <h2 className="mt-1 text-base font-semibold tracking-[-0.02em]">{t('system.backendStatus')}</h2>
              </div>
              <span className="font-mono text-[0.62rem] text-[#8495a8]">{t('system.healthEndpoint')}</span>
            </div>
            <BackendStatus connection={connection} />
            <div className="mt-5 border-t border-[#dce7f1] pt-5 text-sm leading-6 text-[#536b83]">
              <p className="font-semibold text-[#294765]">{t('analysis.page.scopeTitle')}</p>
              <p className="mt-1">{t('analysis.page.scopeDescription')}</p>
            </div>
          </aside>
        </div>

        {result ? (
          <section className="mt-8 border-t border-[#dce7f1] pt-8 lg:mt-10 lg:pt-10">
            <AnalysisWorkspace result={result} />
          </section>
        ) : null}
      </main>

      <footer className="border-t border-[#dce7f1] bg-white">
        <div className="mx-auto flex w-full max-w-[1440px] flex-wrap items-center justify-between gap-2 px-4 py-4 font-mono text-[0.62rem] uppercase tracking-[0.1em] text-[#788a9e] sm:px-6 md:px-8 lg:px-10 xl:px-12 2xl:px-16">
          <span>{t('system.technology')}</span>
          <span>{t('analysis.page.footer')}</span>
        </div>
      </footer>
    </div>
  )
}
