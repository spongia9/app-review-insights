import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  ApiError,
  getAnalysisRun,
  getFindingCandidates,
  getFindings,
  getTopics,
  startEvidenceValidation,
  startSemanticAnalysis,
} from '../api/client'
import type {
  AnalysisRunView,
  EvidenceValidationAudit,
  Finding,
  FindingCandidate,
  FindingStatus,
  IngestionResult,
  TopicCandidate,
} from '../types/analysis'
import { ProductPlanningPanel } from './ProductPlanningPanel'

interface SemanticAnalysisPanelProps {
  ingestion: IngestionResult
}

const evidenceStages = new Set([
  'EVIDENCE_VALIDATION',
  'CONFLICT_ANALYSIS',
  'FINDING_FINALIZATION',
])

const statusTone: Record<FindingStatus, string> = {
  SUPPORTED: 'bg-[#e8f7f0] text-[#166a4a]',
  WEAK: 'bg-[#fff5df] text-[#7a5a17]',
  CONFLICTED: 'bg-[#fff0e6] text-[#8a481d]',
  INSUFFICIENT: 'bg-[#eef2f6] text-[#52677c]',
  UNSUPPORTED: 'bg-[#fff0f0] text-[#8b3434]',
}

export function SemanticAnalysisPanel({ ingestion }: SemanticAnalysisPanelProps) {
  const { t, i18n } = useTranslation()
  const [runView, setRunView] = useState<AnalysisRunView | null>(null)
  const [topics, setTopics] = useState<TopicCandidate[]>([])
  const [candidates, setCandidates] = useState<FindingCandidate[]>([])
  const [validatedFindings, setValidatedFindings] = useState<Finding[]>([])
  const [audits, setAudits] = useState<EvidenceValidationAudit[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isStartingSemantic, setIsStartingSemantic] = useState(false)
  const [isStartingEvidence, setIsStartingEvidence] = useState(false)

  const reviewById = useMemo(
    () => new Map(ingestion.reviews.map((review) => [review.id, review])),
    [ingestion.reviews],
  )
  const auditByCandidateId = useMemo(
    () => new Map(audits.map((audit) => [audit.finding_candidate_id, audit])),
    [audits],
  )

  const status = runView?.run.status
  const isActive = status === 'PENDING' || status === 'RUNNING'
  const isEvidencePhase = Boolean(
    runView?.evidence_validation ||
      (runView && evidenceStages.has(runView.run.current_stage)) ||
      (runView?.run.last_successful_stage && evidenceStages.has(runView.run.last_successful_stage)),
  )
  const canResumeConsolidation = Boolean(
    status === 'FAILED' &&
      !isEvidencePhase &&
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
        if (next.run.status === 'COMPLETED' || next.run.status === 'WARNING') {
          if (next.semantic_analysis) {
            const [topicView, candidateView] = await Promise.all([
              getTopics(ingestion.analysis_run_id),
              getFindingCandidates(ingestion.analysis_run_id),
            ])
            setTopics(topicView.topics)
            setCandidates(candidateView.finding_candidates)
          }
          if (next.evidence_validation) {
            const findingView = await getFindings(ingestion.analysis_run_id)
            setValidatedFindings(findingView.findings)
            setAudits(findingView.audits)
          }
        }
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : t('analysis.semantic.errors.poll'))
      }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [ingestion.analysis_run_id, isActive, t])

  const handleStartSemantic = async () => {
    setError(null)
    setTopics([])
    setCandidates([])
    setValidatedFindings([])
    setAudits([])
    setIsStartingSemantic(true)
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
      setIsStartingSemantic(false)
    }
  }

  const handleStartEvidence = async () => {
    setError(null)
    setValidatedFindings([])
    setAudits([])
    setIsStartingEvidence(true)
    try {
      const next = await startEvidenceValidation(ingestion.analysis_run_id)
      setRunView(next)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t('analysis.evidence.errors.start'))
    } finally {
      setIsStartingEvidence(false)
    }
  }

  const semanticSummary = runView?.semantic_analysis
  const evidenceSummary = runView?.evidence_validation
  const failureCode = runView?.run.error_code
  const stageLabel =
    status === 'COMPLETED' || status === 'WARNING'
      ? t(evidenceSummary ? 'analysis.evidence.completed' : 'analysis.semantic.completed')
      : runView
        ? t(`analysis.stages.${runView.run.current_stage}`, { defaultValue: runView.run.current_stage })
        : ''
  const failureMessage = failureCode
    ? t(`analysis.semantic.errorCodes.${failureCode}`, {
        defaultValue: t(isEvidencePhase ? 'analysis.evidence.errors.start' : 'analysis.semantic.errors.start'),
      })
    : error ?? runView?.run.errors.join(' ') ?? t('analysis.semantic.errors.start')
  const showSemanticStart = !runView || (status === 'FAILED' && !isEvidencePhase)
  const showEvidenceStart = Boolean(
    semanticSummary &&
      candidates.length > 0 &&
      !isActive &&
      (!evidenceSummary || (status === 'FAILED' && isEvidencePhase)),
  )

  const formatPercent = (value: number) =>
    new Intl.NumberFormat(i18n.resolvedLanguage ?? 'zh-CN', {
      style: 'percent',
      maximumFractionDigits: 0,
    }).format(value)

  return (
    <section className="mt-10 border-t border-[#d7e3ee] pt-8" data-testid="semantic-analysis">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-[-0.025em] text-[#15314f]">{t('analysis.semantic.title')}</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-[#61748a]">{t('analysis.semantic.description')}</p>
        </div>
        {showSemanticStart ? (
          <button
            className="min-h-11 rounded-xl bg-[#175bd8] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#104ebd] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#175bd8] disabled:bg-[#8aaad7]"
            data-testid="start-semantic-analysis"
            disabled={isStartingSemantic}
            onClick={handleStartSemantic}
            type="button"
          >
            {isStartingSemantic
              ? t(canResumeConsolidation ? 'analysis.semantic.resuming' : 'analysis.semantic.starting')
              : t(canResumeConsolidation ? 'analysis.semantic.retryConsolidation' : 'analysis.semantic.start')}
          </button>
        ) : null}
      </div>

      {runView ? (
        <div className="mt-5 border-y border-[#d7e3ee] py-4" data-testid="analysis-progress">
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
          <p className="break-words font-medium">{failureMessage}</p>
          {canResumeConsolidation ? <p className="mt-1 text-xs leading-5 text-[#8b4a4a]">{t('analysis.semantic.resumeHint')}</p> : null}
          {failureCode && runView?.run.errors.length ? (
            <details className="mt-2 text-xs">
              <summary className="cursor-pointer font-medium">{t('analysis.semantic.technicalDetails')}</summary>
              <p className="mt-1 break-words font-mono leading-5">{failureCode}: {runView.run.errors.join(' ')}</p>
            </details>
          ) : null}
        </div>
      ) : null}

      {semanticSummary ? (
        <>
          <dl className="mt-6 grid gap-px overflow-hidden rounded-xl border border-[#d7e3ee] bg-[#d7e3ee] sm:grid-cols-2 lg:grid-cols-5">
            {[
              ['analyzed', `${semanticSummary.analyzed_review_count}/${semanticSummary.total_review_count}`],
              ['batches', String(semanticSummary.batch_count)],
              ['model', semanticSummary.model_name],
              ['language', t(`analysis.outputLanguage.${semanticSummary.resolved_output_language}`)],
              ['goal', semanticSummary.analysis_goal || t('analysis.semantic.noGoal')],
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
                {candidates.map((finding) => (
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

      {semanticSummary && candidates.length ? (
        <section className="mt-10 border-t border-[#d7e3ee] pt-8" data-testid="evidence-validation">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h3 className="text-lg font-semibold tracking-[-0.02em] text-[#15314f]">{t('analysis.evidence.title')}</h3>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-[#61748a]">{t('analysis.evidence.description')}</p>
            </div>
            {showEvidenceStart ? (
              <button
                className="min-h-11 rounded-xl bg-[#173f73] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#123560] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#173f73] disabled:bg-[#8aa0b8]"
                data-testid="start-evidence-validation"
                disabled={isStartingEvidence}
                onClick={handleStartEvidence}
                type="button"
              >
                {isStartingEvidence ? t('analysis.evidence.starting') : t('analysis.evidence.start')}
              </button>
            ) : null}
          </div>

          {evidenceSummary ? (
            <dl className="mt-5 flex flex-wrap gap-x-8 gap-y-3 border-y border-[#d7e3ee] py-4 text-sm">
              <div>
                <dt className="text-xs text-[#6a7e92]">{t('analysis.evidence.info.findings')}</dt>
                <dd className="mt-1 font-mono font-semibold text-[#17304d]">{evidenceSummary.validated_candidate_count}/{evidenceSummary.total_candidate_count}</dd>
              </div>
              <div>
                <dt className="text-xs text-[#6a7e92]">{t('analysis.evidence.info.reviews')}</dt>
                <dd className="mt-1 font-mono font-semibold text-[#17304d]">{evidenceSummary.validated_review_count}</dd>
              </div>
              <div>
                <dt className="text-xs text-[#6a7e92]">{t('analysis.evidence.info.batches')}</dt>
                <dd className="mt-1 font-mono font-semibold text-[#17304d]">{evidenceSummary.batch_count}</dd>
              </div>
              <div>
                <dt className="text-xs text-[#6a7e92]">{t('analysis.evidence.info.model')}</dt>
                <dd className="mt-1 font-semibold text-[#17304d]">{evidenceSummary.model_name}</dd>
              </div>
            </dl>
          ) : null}

          <div className="mt-6 space-y-5">
            {validatedFindings.map((finding) => {
              const audit = auditByCandidateId.get(finding.validation_metadata.finding_candidate_id)
              return (
                <article className="rounded-xl border border-[#d7e3ee] bg-white p-4 sm:p-5" key={finding.id}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-[#175bd8]">{finding.topic}</p>
                      <h4 className="mt-1.5 text-base font-semibold text-[#17304d]">{finding.title}</h4>
                      <p className="mt-2 max-w-4xl text-sm leading-6 text-[#526a82]">{finding.problem}</p>
                    </div>
                    <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${statusTone[finding.status]}`}>
                      {t(`findingStatus.${finding.status}`)}
                    </span>
                  </div>

                  <dl className="mt-4 flex flex-wrap gap-x-7 gap-y-3 border-y border-[#e1eaf2] py-3 text-sm">
                    <div><dt className="text-xs text-[#6a7e92]">{t('terms.supportingEvidence')}</dt><dd className="mt-0.5 font-mono font-semibold text-[#166a4a]">{finding.support_count}</dd></div>
                    <div><dt className="text-xs text-[#6a7e92]">{t('terms.conflictingEvidence')}</dt><dd className="mt-0.5 font-mono font-semibold text-[#8a481d]">{finding.conflict_count}</dd></div>
                    <div><dt className="text-xs text-[#6a7e92]">{t('terms.evidenceStrength')}</dt><dd className="mt-0.5 font-semibold text-[#294765]">{t(`analysis.evidence.strength.${finding.evidence_strength}`)}</dd></div>
                    <div><dt className="text-xs text-[#6a7e92]">{t('terms.confidence')}</dt><dd className="mt-0.5 font-mono font-semibold text-[#294765]">{formatPercent(finding.confidence)}</dd></div>
                  </dl>

                  <div className="mt-4 grid gap-4 lg:grid-cols-2">
                    <div>
                      <p className="text-xs font-semibold text-[#526a82]">{t('analysis.evidence.uncertainty')}</p>
                      <p className="mt-1 text-sm leading-6 text-[#526a82]">{finding.uncertainty}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-[#526a82]">{t('analysis.evidence.limitations')}</p>
                      <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-5 text-[#61748a]">
                        {finding.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
                      </ul>
                    </div>
                  </div>

                  {audit ? (
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      {[
                        { kind: 'supporting', reviewIds: finding.supporting_review_ids },
                        { kind: 'conflicting', reviewIds: finding.conflicting_review_ids },
                      ].map(({ kind, reviewIds }) => (
                        <details className="rounded-lg bg-[#f6f9fc] p-3" key={kind}>
                          <summary className="cursor-pointer text-xs font-semibold text-[#175bd8]">
                            {t(`analysis.evidence.view.${kind}`, { count: reviewIds.length })}
                          </summary>
                          <div className="mt-3 space-y-3">
                            {reviewIds.length ? reviewIds.map((reviewId) => {
                              const sourceReview = reviewById.get(reviewId)
                              const judgment = audit.judgments.find((item) => item.review_id === reviewId)
                              return sourceReview && judgment ? (
                                <div className="border-t border-[#dce7f1] pt-3 first:border-t-0 first:pt-0" key={reviewId}>
                                  <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[0.68rem] text-[#657a90]">
                                    <span className="font-semibold text-[#294765]">{reviewId}</span>
                                    <span>{t('analysis.table.rating')}: {sourceReview.rating ?? '—'}</span>
                                    <span>{t('analysis.table.version')}: {sourceReview.version ?? '—'}</span>
                                    <span>{t('analysis.evidence.stanceLabel')}: {t(`analysis.evidence.stance.${judgment.stance}`)}</span>
                                  </div>
                                  <blockquote className="mt-2 text-xs leading-5 text-[#405a73]">{sourceReview.text}</blockquote>
                                  <p className="mt-2 text-xs leading-5 text-[#61748a]"><span className="font-semibold">{t('analysis.evidence.reason')}:</span> {judgment.reason}</p>
                                </div>
                              ) : null
                            }) : <p className="text-xs text-[#74879a]">{t('analysis.evidence.noEvidence')}</p>}
                          </div>
                        </details>
                      ))}
                    </div>
                  ) : null}
                </article>
              )
            })}
          </div>
        </section>
      ) : null}
      {evidenceSummary && validatedFindings.length ? (
        <ProductPlanningPanel
          analysisRunId={ingestion.analysis_run_id}
          findings={validatedFindings}
          reviews={ingestion.reviews}
        />
      ) : null}
    </section>
  )
}
