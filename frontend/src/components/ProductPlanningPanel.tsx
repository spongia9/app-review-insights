import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  ApiError,
  apiBaseUrl,
  getAnalysisRun,
  getProductPlan,
  startProductPlanning,
} from '../api/client'
import type {
  AnalysisRunView,
  Finding,
  ProductPlanningResult,
  Requirement,
  Review,
} from '../types/analysis'

interface ProductPlanningPanelProps {
  analysisRunId: string
  findings: Finding[]
  reviews: Review[]
}

const planningStages = new Set([
  'REQUIREMENT_GENERATION',
  'VERSION_PLANNING',
  'PRD_GENERATION',
  'TEST_CASE_GENERATION',
  'TRACEABILITY_VALIDATION',
])

export function ProductPlanningPanel({
  analysisRunId,
  findings,
  reviews,
}: ProductPlanningPanelProps) {
  const { t, i18n } = useTranslation()
  const [runView, setRunView] = useState<AnalysisRunView | null>(null)
  const [planning, setPlanning] = useState<ProductPlanningResult | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const findingById = useMemo(
    () => new Map(findings.map((finding) => [finding.id, finding])),
    [findings],
  )
  const reviewById = useMemo(
    () => new Map(reviews.map((review) => [review.id, review])),
    [reviews],
  )
  const requirementById = useMemo(
    () => new Map((planning?.requirements ?? []).map((requirement) => [requirement.id, requirement])),
    [planning?.requirements],
  )

  const status = runView?.run.status
  const hasEligibleFindings = findings.some((finding) => finding.status === 'SUPPORTED')
  const isActive = status === 'PENDING' || status === 'RUNNING'
  const isPlanningFailure = Boolean(
    status === 'FAILED' &&
      (planningStages.has(runView?.run.current_stage ?? '') ||
        planningStages.has(runView?.run.last_successful_stage ?? '')),
  )

  useEffect(() => {
    if (!isActive) return
    const timer = window.setInterval(async () => {
      try {
        const nextRun = await getAnalysisRun(analysisRunId)
        setRunView(nextRun)
        if (
          nextRun.product_planning &&
          (nextRun.run.status === 'COMPLETED' || nextRun.run.status === 'WARNING')
        ) {
          const view = await getProductPlan(analysisRunId)
          setPlanning(view.product_planning)
        }
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : t('analysis.planning.errors.poll'))
      }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [analysisRunId, isActive, t])

  const handleStart = async () => {
    setError(null)
    setPlanning(null)
    setIsStarting(true)
    try {
      const nextRun = await startProductPlanning(analysisRunId)
      setRunView(nextRun)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t('analysis.planning.errors.start'))
    } finally {
      setIsStarting(false)
    }
  }

  const formatPercent = (value: number | null) =>
    value === null
      ? t('analysis.planning.notApplicable')
      : new Intl.NumberFormat(i18n.resolvedLanguage ?? 'zh-CN', {
          style: 'percent',
          maximumFractionDigits: 0,
        }).format(value)

  const stageLabel = runView
    ? status === 'COMPLETED' || status === 'WARNING'
      ? t('analysis.planning.completed')
      : t(`analysis.stages.${runView.run.current_stage}`, {
          defaultValue: runView.run.current_stage,
        })
    : ''

  return (
    <section className="mt-10 border-t border-[#d7e3ee] pt-8" data-testid="product-planning">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold tracking-[-0.02em] text-[#15314f]">
            {t('analysis.planning.title')}
          </h3>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[#61748a]">
            {t('analysis.planning.description')}
          </p>
        </div>
        {!planning && !isActive && hasEligibleFindings ? (
          <button
            className="min-h-11 rounded-xl bg-[#173f73] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#123560] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#173f73] disabled:bg-[#8aa0b8]"
            data-testid="start-product-planning"
            disabled={isStarting}
            onClick={handleStart}
            type="button"
          >
            {isStarting ? t('analysis.planning.starting') : t(isPlanningFailure ? 'analysis.planning.retry' : 'analysis.planning.start')}
          </button>
        ) : null}
      </div>

      {!hasEligibleFindings ? (
        <p className="mt-5 rounded-xl bg-[#fff5df] px-4 py-3 text-sm leading-6 text-[#70551c]">
          {t('analysis.planning.noEligibleFindings')}
        </p>
      ) : null}

      {runView && (isActive || planning) ? (
        <div className="mt-5 border-y border-[#d7e3ee] py-4" data-testid="product-planning-progress">
          <div className="flex items-center justify-between gap-4 text-xs text-[#5f748a]">
            <span>{stageLabel}</span>
            <span className="font-mono">{runView.run.progress}%</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#dce7f1]">
            <div className="h-full bg-[#173f73]" style={{ width: `${runView.run.progress}%` }} />
          </div>
        </div>
      ) : null}

      {error || isPlanningFailure ? (
        <div className="mt-5 rounded-xl bg-[#fff1f1] px-4 py-3 text-sm leading-6 text-[#8b3434]" role="alert">
          <p className="break-words font-medium">
            {error ?? runView?.run.errors.join(' ') ?? t('analysis.planning.errors.start')}
          </p>
          <p className="mt-1 text-xs">{t('analysis.planning.failureSafety')}</p>
        </div>
      ) : null}

      {planning ? (
        <div className="mt-7 space-y-10">
          <PlanningSummary planning={planning} formatPercent={formatPercent} />
          <RequirementsSection
            findingById={findingById}
            planning={planning}
            reviewById={reviewById}
          />
          <VersionPlanSection planning={planning} requirementById={requirementById} />
          <PrdSection planning={planning} />
          <TestCasesSection planning={planning} requirementById={requirementById} />
        </div>
      ) : null}
    </section>
  )
}

function PlanningSummary({
  planning,
  formatPercent,
}: {
  planning: ProductPlanningResult
  formatPercent: (value: number | null) => string
}) {
  const { t } = useTranslation()
  const summary = [
    ['requirements', String(planning.requirements.length)],
    ['versions', String(planning.version_plan?.items.length ?? 0)],
    ['tests', String(planning.test_cases.length)],
    ['traceability', formatPercent(planning.traceability?.overall_traceability_coverage ?? null)],
    ['model', planning.model_name],
  ]
  return (
    <dl className="grid gap-px overflow-hidden rounded-xl border border-[#d7e3ee] bg-[#d7e3ee] sm:grid-cols-2 lg:grid-cols-5">
      {summary.map(([key, value]) => (
        <div className="min-w-0 bg-white px-4 py-3" key={key}>
          <dt className="text-xs text-[#6a7e92]">{t(`analysis.planning.info.${key}`)}</dt>
          <dd className="mt-1 truncate text-sm font-semibold text-[#17304d]" title={value}>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function RequirementsSection({
  planning,
  findingById,
  reviewById,
}: {
  planning: ProductPlanningResult
  findingById: Map<string, Finding>
  reviewById: Map<string, Review>
}) {
  const { t } = useTranslation()
  return (
    <section data-testid="product-requirements">
      <h4 className="text-base font-semibold text-[#17304d]">{t('analysis.planning.requirements.title')}</h4>
      <div className="mt-3 divide-y divide-[#dfe8f0] border-y border-[#d7e3ee]">
        {planning.requirements.map((requirement) => (
          <article className="py-5" key={requirement.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-md bg-[#eaf1fc] px-2 py-1 font-mono text-xs font-bold text-[#175bd8]">{requirement.priority}</span>
                  <span className="text-xs text-[#6a7e92]">{t(`artifactValidation.${requirement.validation_result}`)}</span>
                </div>
                <h5 className="mt-2 font-semibold text-[#17304d]">{requirement.title}</h5>
                <p className="mt-1.5 max-w-4xl text-sm leading-6 text-[#526a82]">{requirement.user_problem}</p>
              </div>
              <span className="font-mono text-xs text-[#60778e]">
                {t('analysis.planning.requirements.evidenceCount', { count: requirement.review_ids.length })}
              </span>
            </div>
            <div className="mt-4">
              <p className="text-xs font-semibold text-[#526a82]">{t('analysis.planning.acceptanceCriteria')}</p>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-6 text-[#526a82]">
                {requirement.acceptance_criteria.map((criterion) => <li key={criterion}>{criterion}</li>)}
              </ul>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <SourceFindings requirement={requirement} findingById={findingById} />
              <SourceReviews requirement={requirement} reviewById={reviewById} />
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}

function SourceFindings({ requirement, findingById }: { requirement: Requirement; findingById: Map<string, Finding> }) {
  const { t } = useTranslation()
  return (
    <details className="rounded-lg bg-[#f6f9fc] p-3">
      <summary className="cursor-pointer text-xs font-semibold text-[#175bd8]">
        {t('analysis.planning.requirements.viewFindings', { count: requirement.finding_ids.length })}
      </summary>
      <div className="mt-3 space-y-3">
        {requirement.finding_ids.map((findingId) => {
          const finding = findingById.get(findingId)
          return finding ? (
            <div className="border-t border-[#dce7f1] pt-3 first:border-t-0 first:pt-0" key={findingId}>
              <p className="font-mono text-[0.68rem] text-[#61748a]">{findingId}</p>
              <p className="mt-1 text-xs font-semibold text-[#294765]">{finding.title}</p>
              <p className="mt-1 text-xs leading-5 text-[#61748a]">{finding.problem}</p>
            </div>
          ) : null
        })}
      </div>
    </details>
  )
}

function SourceReviews({ requirement, reviewById }: { requirement: Requirement; reviewById: Map<string, Review> }) {
  const { t } = useTranslation()
  return (
    <details className="rounded-lg bg-[#f6f9fc] p-3">
      <summary className="cursor-pointer text-xs font-semibold text-[#175bd8]">
        {t('analysis.planning.requirements.viewReviews', { count: requirement.review_ids.length })}
      </summary>
      <div className="mt-3 max-h-72 space-y-3 overflow-y-auto">
        {requirement.review_ids.map((reviewId) => {
          const review = reviewById.get(reviewId)
          return review ? (
            <blockquote className="border-t border-[#dce7f1] pt-3 text-xs leading-5 text-[#536b83] first:border-t-0 first:pt-0" key={reviewId}>
              <span className="font-mono font-semibold text-[#294765]">{reviewId}</span>{' '}
              {review.text}
            </blockquote>
          ) : null
        })}
      </div>
    </details>
  )
}

function VersionPlanSection({
  planning,
  requirementById,
}: {
  planning: ProductPlanningResult
  requirementById: Map<string, Requirement>
}) {
  const { t } = useTranslation()
  if (!planning.version_plan) return null
  return (
    <section data-testid="version-plan">
      <h4 className="text-base font-semibold text-[#17304d]">{t('analysis.planning.versionPlan.title')}</h4>
      <p className="mt-1 text-sm leading-6 text-[#61748a]">{planning.version_plan.summary}</p>
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        {planning.version_plan.items.map((item) => (
          <article className="rounded-xl border border-[#d7e3ee] bg-white p-4" key={item.id}>
            <p className="font-mono text-xs font-semibold text-[#175bd8]">{item.version}</p>
            <h5 className="mt-1.5 font-semibold text-[#17304d]">{item.theme}</h5>
            <p className="mt-2 text-sm leading-6 text-[#526a82]">{item.goal}</p>
            <ul className="mt-3 space-y-1.5 text-xs leading-5 text-[#405a73]">
              {item.requirement_ids.map((requirementId) => (
                <li key={requirementId}>• {requirementById.get(requirementId)?.title ?? requirementId}</li>
              ))}
            </ul>
            <p className="mt-3 border-t border-[#e1eaf2] pt-3 text-xs leading-5 text-[#61748a]">
              <span className="font-semibold">{t('analysis.planning.versionPlan.rationale')}:</span> {item.rationale}
            </p>
          </article>
        ))}
      </div>
    </section>
  )
}

function PrdSection({ planning }: { planning: ProductPlanningResult }) {
  const { t } = useTranslation()
  const artifact = planning.prd_artifact
  if (!artifact) return null
  const prd = artifact.structured_prd
  return (
    <section data-testid="structured-prd">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h4 className="text-base font-semibold text-[#17304d]">{t('analysis.planning.prd.title')}</h4>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-[#6a7e92]">{t(`artifactValidation.${artifact.validation_result}`)}</span>
          <a
            className="font-semibold text-[#175bd8] hover:text-[#104ebd] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#175bd8]"
            download="PRD.md"
            href={`${apiBaseUrl}/api/analysis/${planning.analysis_run_id}/product-plan/prd.md`}
          >
            {t('analysis.planning.prd.download')}
          </a>
        </div>
      </div>
      <article className="mt-3 rounded-xl border border-[#d7e3ee] bg-white p-4 sm:p-5">
        <h5 className="text-lg font-semibold text-[#17304d]">{prd.title}</h5>
        <p className="mt-2 text-sm leading-6 text-[#405a73]">{prd.product_goal}</p>
        <div className="mt-5 grid gap-5 md:grid-cols-2">
          {[
            ['background', prd.background],
            ['scope', prd.analysis_scope],
          ].map(([key, value]) => (
            <div key={key}>
              <p className="text-xs font-semibold text-[#526a82]">{t(`analysis.planning.prd.${key}`)}</p>
              <p className="mt-1 text-sm leading-6 text-[#526a82]">{value}</p>
            </div>
          ))}
        </div>
        <div className="mt-5 divide-y divide-[#e1eaf2] border-y border-[#e1eaf2]">
          {prd.requirements.map((section) => (
            <div className="py-3" key={section.id}>
              <p className="text-sm font-semibold text-[#294765]">{section.title}</p>
              <p className="mt-1 text-sm leading-6 text-[#61748a]">{section.content}</p>
            </div>
          ))}
        </div>
        <details className="mt-4 rounded-lg bg-[#f6f9fc] p-3">
          <summary className="cursor-pointer text-xs font-semibold text-[#175bd8]">{t('analysis.planning.prd.viewMarkdown')}</summary>
          <pre className="mt-3 max-h-[32rem] overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-5 text-[#405a73]">{artifact.rendered_markdown}</pre>
        </details>
      </article>
    </section>
  )
}

function TestCasesSection({
  planning,
  requirementById,
}: {
  planning: ProductPlanningResult
  requirementById: Map<string, Requirement>
}) {
  const { t } = useTranslation()
  return (
    <section data-testid="test-cases">
      <h4 className="text-base font-semibold text-[#17304d]">{t('analysis.planning.testCases.title')}</h4>
      <div className="mt-3 space-y-4">
        {planning.test_cases.map((testCase) => (
          <article className="rounded-xl border border-[#d7e3ee] bg-white p-4" key={testCase.id}>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="rounded-md bg-[#edf3f9] px-2 py-1 font-mono font-semibold text-[#294765]">{testCase.test_type}</span>
              <span className="font-mono text-[#175bd8]">{testCase.priority}</span>
              <span className="text-[#6a7e92]">{t('analysis.planning.testCases.sourceCount', { count: testCase.source_review_ids.length })}</span>
            </div>
            <h5 className="mt-2 font-semibold text-[#17304d]">{testCase.title}</h5>
            <p className="mt-1 text-xs text-[#61748a]">
              {t('analysis.planning.testCases.requirement')}: {requirementById.get(testCase.requirement_id)?.title ?? testCase.requirement_id}
            </p>
            <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm leading-6 text-[#526a82]">
              {testCase.steps.map((step) => <li key={step}>{step}</li>)}
            </ol>
            <p className="mt-3 border-t border-[#e1eaf2] pt-3 text-sm leading-6 text-[#405a73]">
              <span className="font-semibold">{t('analysis.planning.testCases.expected')}:</span> {testCase.expected_result}
            </p>
          </article>
        ))}
      </div>
    </section>
  )
}
