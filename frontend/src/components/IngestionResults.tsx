import { useTranslation } from 'react-i18next'

import type { IngestionResult } from '../types/analysis'
import { SemanticAnalysisPanel } from './SemanticAnalysisPanel'

interface IngestionResultsProps {
  result: IngestionResult
}

const statisticKeys = [
  'raw_review_count',
  'clean_review_count',
  'duplicate_count',
  'invalid_count',
] as const

export function IngestionResults({ result }: IngestionResultsProps) {
  const { t, i18n } = useTranslation()
  const { statistics } = result

  if (!statistics) {
    return null
  }

  const formatDate = (value: string | null) => {
    if (!value) return '—'
    return new Intl.DateTimeFormat(i18n.resolvedLanguage ?? 'zh-CN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    }).format(new Date(value))
  }

  return (
    <section className="mt-8" data-testid="ingestion-results">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-[#d7e3ee] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-semibold tracking-[-0.025em] text-[#15314f]">{t('analysis.results.title')}</h2>
            <span className="rounded-full bg-[#edf9f4] px-2.5 py-1 font-mono text-[0.65rem] font-semibold text-[#14784f]">
              {t(`analysis.status.${result.run.status}`)}
            </span>
          </div>
          <p className="mt-1 font-mono text-[0.68rem] text-[#73869a]">{result.analysis_run_id}</p>
        </div>
        <div className="text-right text-xs leading-5 text-[#667b91]">
          <p>{result.provider.source}</p>
          {result.provider.storefront ? (
            <p>
              {t('analysis.results.storefront')}: {result.provider.storefront.toUpperCase()}
            </p>
          ) : null}
        </div>
      </div>

      <dl className="grid grid-cols-2 border-b border-[#d7e3ee] sm:grid-cols-5">
        {statisticKeys.map((key) => (
          <div className="border-r border-[#e1eaf2] px-3 py-4 last:border-r-0 sm:px-4" key={key}>
            <dt className="text-xs leading-5 text-[#6a7e92]">{t(`analysis.statistics.${key}`)}</dt>
            <dd className="mt-1 font-mono text-xl font-semibold text-[#17304d]">{statistics[key]}</dd>
          </div>
        ))}
        <div className="px-3 py-4 sm:px-4">
          <dt className="text-xs leading-5 text-[#6a7e92]">{t('analysis.statistics.retention_rate')}</dt>
          <dd className="mt-1 font-mono text-xl font-semibold text-[#17304d]">
            {new Intl.NumberFormat(i18n.resolvedLanguage ?? 'zh-CN', {
              style: 'percent',
              maximumFractionDigits: 1,
            }).format(statistics.retention_rate)}
          </dd>
        </div>
      </dl>

      {result.run.warnings.length ? (
        <details className="border-b border-[#d7e3ee] py-3 text-sm text-[#675431]">
          <summary className="cursor-pointer font-semibold">{t('analysis.results.limitations')}</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-[#75674c]">
            {result.run.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <div className="mt-5 overflow-x-auto rounded-xl border border-[#d7e3ee]">
        <table className="min-w-[920px] w-full border-collapse text-left text-sm">
          <thead className="bg-[#eef4fa] text-xs font-semibold text-[#526a82]">
            <tr>
              {['rating', 'title', 'text', 'version', 'language', 'date', 'source'].map((column) => (
                <th className="border-b border-[#d7e3ee] px-3 py-3" key={column} scope="col">
                  {t(`analysis.table.${column}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.reviews.map((review) => (
              <tr className="border-b border-[#e4ecf3] last:border-b-0" key={review.id}>
                <td className="px-3 py-3 font-mono text-[#294765]">{review.rating ?? '—'}</td>
                <td className="max-w-44 px-3 py-3 font-medium text-[#294765]">{review.title ?? '—'}</td>
                <td className="min-w-72 max-w-xl px-3 py-3 leading-6 text-[#526a82]">{review.text}</td>
                <td className="px-3 py-3 font-mono text-xs text-[#5f748a]">{review.version ?? '—'}</td>
                <td className="px-3 py-3 font-mono text-xs text-[#5f748a]">{review.language ?? '—'}</td>
                <td className="px-3 py-3 text-xs text-[#5f748a]">{formatDate(review.created_at)}</td>
                <td className="px-3 py-3 font-mono text-[0.68rem] text-[#5f748a]">{review.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <SemanticAnalysisPanel ingestion={result} />
    </section>
  )
}
