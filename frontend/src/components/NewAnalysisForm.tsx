import { useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError, createAppStoreAnalysis, createFileAnalysis } from '../api/client'
import type { AnalysisSource, IngestionResult } from '../types/analysis'

interface NewAnalysisFormProps {
  onComplete: (result: IngestionResult) => void
}

export interface AnalysisFormError {
  code: string
  message: string
  analysisRunId?: string
}

const sources: AnalysisSource[] = ['app_store', 'csv', 'json']

export function NewAnalysisForm({ onComplete }: NewAnalysisFormProps) {
  const { t } = useTranslation()
  const [source, setSource] = useState<AnalysisSource>('app_store')
  const [appStoreUrl, setAppStoreUrl] = useState('')
  const [analysisGoal, setAnalysisGoal] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<AnalysisFormError | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const selectSource = (nextSource: AnalysisSource) => {
    setSource(nextSource)
    setFile(null)
    setError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)

    if (source !== 'app_store' && !file) {
      setError({ code: 'FILE_REQUIRED', message: t('analysis.errors.FILE_REQUIRED') })
      return
    }

    setIsSubmitting(true)
    try {
      const result =
        source === 'app_store'
          ? await createAppStoreAnalysis(appStoreUrl, analysisGoal)
          : await createFileAnalysis(source, file as File, analysisGoal)
      onComplete(result)
    } catch (caughtError) {
      if (caughtError instanceof ApiError) {
        setError({
          code: caughtError.code,
          message: caughtError.message,
          analysisRunId: caughtError.analysisRunId,
        })
      } else {
        setError({ code: 'BACKEND_ERROR', message: t('analysis.errors.BACKEND_ERROR') })
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const localizedError = error
    ? t(`analysis.errors.${error.code}`, { defaultValue: error.message })
    : null

  return (
    <form className="rounded-2xl border border-[#d7e3ee] bg-white p-5 sm:p-6" onSubmit={handleSubmit}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-[-0.025em] text-[#15314f]">{t('analysis.form.title')}</h2>
          <p className="mt-1 max-w-md text-sm leading-6 text-[#61748a]">{t('analysis.form.description')}</p>
        </div>
        <span className="rounded-full bg-[#eaf2ff] px-2.5 py-1 font-mono text-[0.65rem] font-semibold text-[#175bd8]">
          {t('analysis.form.phase')}
        </span>
      </div>

      <fieldset className="mt-6">
        <legend className="text-sm font-semibold text-[#294765]">{t('analysis.form.sourceLabel')}</legend>
        <div className="mt-2 grid grid-cols-3 rounded-xl bg-[#eef4fa] p-1" role="group">
          {sources.map((item) => (
            <button
              aria-pressed={source === item}
              className={`rounded-lg px-2 py-2.5 text-xs font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-[#175bd8] ${
                source === item
                  ? 'bg-white text-[#164f9f] shadow-[0_1px_4px_rgba(20,57,93,0.12)]'
                  : 'text-[#63778d] hover:text-[#294765]'
              }`}
              data-testid={`source-${item}`}
              key={item}
              onClick={() => selectSource(item)}
              type="button"
            >
              {t(`analysis.sources.${item}`)}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="mt-5">
        {source === 'app_store' ? (
          <label className="block">
            <span className="text-sm font-semibold text-[#294765]">{t('analysis.form.appStoreUrl')}</span>
            <input
              className="mt-2 w-full rounded-xl border border-[#cbd9e7] bg-white px-3.5 py-3 text-sm text-[#17304d] outline-none transition-colors placeholder:text-[#75879a] focus:border-[#175bd8] focus:ring-2 focus:ring-[#175bd8]/15"
              data-testid="app-store-url"
              key="app-store-url"
              onChange={(event) => setAppStoreUrl(event.target.value)}
              placeholder={t('analysis.form.appStorePlaceholder')}
              required
              type="url"
              value={appStoreUrl}
            />
          </label>
        ) : (
          <label className="block">
            <span className="text-sm font-semibold text-[#294765]">
              {source === 'csv' ? t('analysis.form.csvFile') : t('analysis.form.jsonFile')}
            </span>
            <input
              accept={source === 'csv' ? '.csv,text/csv' : '.json,application/json'}
              className="mt-2 block w-full rounded-xl border border-[#cbd9e7] bg-[#f8fbfe] px-3 py-3 text-sm text-[#536b83] file:mr-3 file:rounded-lg file:border-0 file:bg-[#175bd8] file:px-3 file:py-2 file:text-xs file:font-semibold file:text-white hover:file:bg-[#104ebd] focus:outline-2 focus:outline-[#175bd8]"
              data-testid="review-file"
              key={`review-file-${source}`}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              ref={fileInputRef}
              required
              type="file"
            />
            <span className="mt-2 block text-xs leading-5 text-[#708397]">{t('analysis.form.uploadHint')}</span>
          </label>
        )}
      </div>

      <label className="mt-5 block">
        <span className="text-sm font-semibold text-[#294765]">{t('analysis.form.goal')}</span>
        <textarea
          className="mt-2 min-h-28 w-full resize-y rounded-xl border border-[#cbd9e7] bg-white px-3.5 py-3 text-sm leading-6 text-[#17304d] outline-none transition-colors placeholder:text-[#75879a] focus:border-[#175bd8] focus:ring-2 focus:ring-[#175bd8]/15"
          maxLength={1000}
          onChange={(event) => setAnalysisGoal(event.target.value)}
          placeholder={t('analysis.form.goalPlaceholder')}
          value={analysisGoal}
        />
        <span className="mt-1 block text-right font-mono text-[0.65rem] text-[#8191a2]">{analysisGoal.length}/1000</span>
      </label>

      {error ? (
        <div className="mt-4 rounded-xl bg-[#fff1f1] px-4 py-3 text-sm leading-6 text-[#8b3434]" role="alert">
          <p className="font-semibold">{localizedError}</p>
          {error.analysisRunId ? (
            <p className="mt-1 font-mono text-[0.68rem] text-[#986262]">
              {t('analysis.form.failedRun')}: {error.analysisRunId}
            </p>
          ) : null}
        </div>
      ) : null}

      <button
        className="mt-5 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-[#175bd8] px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#104ebd] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#175bd8] disabled:cursor-wait disabled:bg-[#8aaad7]"
        data-testid="start-analysis"
        disabled={isSubmitting}
        type="submit"
      >
        {isSubmitting ? t('analysis.form.processing') : t('analysis.form.submit')}
      </button>
    </form>
  )
}
