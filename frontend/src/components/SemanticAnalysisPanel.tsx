import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  ApiError,
  getAnalysisRun,
  getFindingCandidates,
  getTopics,
  startSemanticAnalysis,
} from '../api/client'
import type {
  AnalysisRunView,
  FindingCandidate,
  IngestionResult,
  TopicCandidate,
} from '../types/analysis'

interface SemanticAnalysisPanelProps {
  ingestion: IngestionResult
}

export function SemanticAnalysisPanel({ ingestion }: SemanticAnalysisPanelProps) {
  const { t, i18n } = useTranslation()
  const [runView, setRunView] = useState<AnalysisRunView | null>(null)
  const [topics, setTopics] = useState<TopicCandidate[]>([])
  const [findings, setFindings] = useState<FindingCandidate[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isStarting, setIsStarting] = useState(false)

  const reviewById = useMemo(
    () => new Map(ingestion.reviews.map((review) => [review.id, review])),
    [ingestion.reviews],
  )

  const status = runView?.run.status
  const isActive = status === 'PENDING' || status === 'RUNNING'
  const canResumeConsolidation = Boolean(
    status === 'FAILED' &&
    runView?.semantic_analysis &&
    (runView.run.last_successful_stage === 'FINDING_EXTRACTION' ||
      runView.run.last_successful_stage === 'TOPIC_CONSOLIDATION'),
  )

  useEffect(() => {
    if (!isActive) return
    const timer = window.setInterval(async () => {
      try {
        const next = await getAnalysisRun(ingestion.analysis_run_id)
        setRunView(next)
        if ((next.run.status === 'COMPLETED' || next.run.status === 'WARNING') && next.semantic_analysis) {
          const [topicView, findingView] = await Promise.all([
            getTopics(ingestion.analysis_run_id),
            getFindingCandidates(ingestion.analysis_run_id),
          ])
          setTopics(topicView.topics)
          setFindings(findingView.finding_candidates)
        }
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : t('analysis.semantic.errors.poll'))
      }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [ingestion.analysis_run_id, isActive, t])

  const handleStart = async () => {
    setError(null)
    setTopics([])
    setFindings([])
    setIsStarting(true)
    try {
      const next = await startSemanticAnalysis(
        ingestion.analysis_run_id,
        ingestion.run.output_language,
        i18n.resolvedLanguage ?? 'zh-CN',
      )
      setRunView(next)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t('analysis.semantic.errors.start'))
    } finally {
      setIsStarting(false)
    }
  }

  const summary = runView?.semantic_analysis
  const failureCode = runView?.run.error_code
  const stageLabel =
    status === 'COMPLETED' || status === 'WARNING'
      ? t('analysis.semantic.completed')
      : runView
        ? t(`analysis.stages.${runView.run.current_stage}`, { defaultValue: runView.run.current_stage })
        : ''
  const failureMessage = failureCode
    ? t(`analysis.semantic.errorCodes.${failureCode}`, {
        defaultValue: t('analysis.semantic.errors.start'),
      })
    : error ?? runView?.run.errors.join(' ') ?? t('analysis.semantic.errors.start')

  return (
    <section className="mt-10 border-t border-[#d7e3ee] pt-8" data-testid="semantic-analysis">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-[-0.025em] text-[#15314f]">{t('analysis.semantic.title')}</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-[#61748a]">{t('analysis.semantic.description')}</p>
        </div>
        {!runView || status === 'FAILED' ? (
          <button
            className="min-h-11 rounded-xl bg-[#175bd8] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#104ebd] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#175bd8] disabled:bg-[#8aaad7]"
            data-testid="start-semantic-analysis"
            disabled={isStarting}
            onClick={handleStart}
            type="button"
          >
            {isStarting
              ? t(canResumeConsolidation ? 'analysis.semantic.resuming' : 'analysis.semantic.starting')
              : t(canResumeConsolidation ? 'analysis.semantic.retryConsolidation' : 'analysis.semantic.start')}
          </button>
        ) : null}
      </div>

      {runView ? (
        <div className="mt-5 border-y border-[#d7e3ee] py-4" data-testid="semantic-progress">
          <div className="flex items-center justify-between gap-4 text-xs text-[#5f748a]">
            <span>{stageLabel}</span>
            <span className="font-mono">{runView.run.progress}%</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#dce7f1]">
            <div className="h-full bg-[#175bd8]" style={{ width: `${runView.run.progress}%` }} />
          </div>
        </div>
      ) : null}

      {error || status === 'FAILED' ? (
        <div className="mt-5 rounded-xl bg-[#fff1f1] px-4 py-3 text-sm leading-6 text-[#8b3434]" role="alert">
          <p className="font-medium break-words">
            {failureMessage}
          </p>
          {canResumeConsolidation ? (
            <p className="mt-1 text-xs leading-5 text-[#8b4a4a]">
              {t('analysis.semantic.resumeHint')}
            </p>
          ) : null}
          {failureCode && runView?.run.errors.length ? (
            <details className="mt-2 text-xs">
              <summary className="cursor-pointer font-medium">
                {t('analysis.semantic.technicalDetails')}
              </summary>
              <p className="mt-1 break-words font-mono leading-5">
                {failureCode}: {runView.run.errors.join(' ')}
              </p>
            </details>
          ) : null}
        </div>
      ) : null}

      {summary ? (
        <>
          <dl className="mt-6 grid gap-px overflow-hidden rounded-xl border border-[#d7e3ee] bg-[#d7e3ee] sm:grid-cols-2 lg:grid-cols-5">
            {[
              ['analyzed', `${summary.analyzed_review_count}/${summary.total_review_count}`],
              ['batches', String(summary.batch_count)],
              ['model', summary.model_name],
              ['language', t(`analysis.outputLanguage.${summary.resolved_output_language}`)],
              ['goal', summary.analysis_goal || t('analysis.semantic.noGoal')],
            ].map(([key, value]) => (
              <div className="min-w-0 bg-white px-4 py-3" key={key}>
                <dt className="text-xs text-[#6a7e92]">{t(`analysis.semantic.info.${key}`)}</dt>
                <dd className="mt-1 truncate text-sm font-semibold text-[#17304d]" title={value}>{value}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-8 grid min-w-0 gap-8 lg:grid-cols-[minmax(15rem,0.72fr)_minmax(0,1.28fr)]">
            <section className="min-w-0">
              <h3 className="text-base font-semibold text-[#17304d]">{t('analysis.semantic.topics')}</h3>
              <div className="mt-3 divide-y divide-[#e0e9f1] border-y border-[#d7e3ee]">
                {topics.map((topic) => (
                  <div className="py-3" key={topic.id}>
                    <div className="flex items-start justify-between gap-3">
                      <p className="font-semibold text-[#294765]">{topic.name}</p>
                      <span className="shrink-0 font-mono text-xs text-[#175bd8]">{topic.review_ids.length}</span>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-[#61748a]">{topic.summary}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="min-w-0">
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="text-base font-semibold text-[#17304d]">{t('analysis.semantic.findings')}</h3>
                <span className="text-xs text-[#7a8ca0]">{t('analysis.semantic.unvalidated')}</span>
              </div>
              <div className="mt-3 space-y-4">
                {findings.map((finding) => (
                  <article className="rounded-xl border border-[#d7e3ee] bg-white p-4" key={finding.id}>
                    <p className="text-xs font-semibold text-[#175bd8]">{finding.topic}</p>
                    <h4 className="mt-1.5 font-semibold text-[#17304d]">{finding.title}</h4>
                    <p className="mt-2 text-sm leading-6 text-[#526a82]">{finding.problem}</p>
                    <details className="mt-3 border-t border-[#e1eaf2] pt-3">
                      <summary className="cursor-pointer text-xs font-semibold text-[#175bd8]">
                        {t('analysis.semantic.viewReviews', { count: finding.supporting_review_ids.length })}
                      </summary>
                      <div className="mt-3 space-y-3">
                        {finding.supporting_review_ids.map((reviewId) => {
                          const sourceReview = reviewById.get(reviewId)
                          return sourceReview ? (
                            <blockquote className="text-xs leading-5 text-[#536b83]" key={reviewId}>
                              <span className="font-mono font-semibold text-[#294765]">{reviewId}</span>{' '}
                              {sourceReview.text}
                            </blockquote>
                          ) : null
                        })}
                      </div>
                    </details>
                  </article>
                ))}
              </div>
            </section>
          </div>
        </>
      ) : null}
    </section>
  )
}
