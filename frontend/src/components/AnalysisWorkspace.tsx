import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  ApiError,
  getAnalysisRun,
  getFindingCandidates,
  getFindings,
  getProductPlan,
  getTopics,
  getTraceability,
} from '../api/client'
import type {
  AnalysisRun,
  AnalysisRunView,
  FindingCandidatesView,
  FindingsView,
  IngestionResult,
  ProductPlanningResult,
  TopicCandidate,
  TraceabilityView,
} from '../types/analysis'
import { WorkspacePanel } from './WorkspacePanels'

export type WorkspaceTab =
  | 'overview'
  | 'reviews'
  | 'cleaning'
  | 'topics'
  | 'findings'
  | 'requirements'
  | 'versions'
  | 'prd'
  | 'tests'
  | 'traceability'
  | 'audit'

const tabs: WorkspaceTab[] = [
  'overview',
  'reviews',
  'cleaning',
  'topics',
  'findings',
  'requirements',
  'versions',
  'prd',
  'tests',
  'traceability',
  'audit',
]

const stageOrder = [
  'SCOPE_RESOLUTION',
  'DATA_ACQUISITION',
  'CLEANING_AND_NORMALIZATION',
  'SEMANTIC_TOPIC_DISCOVERY',
  'FINDING_EXTRACTION',
  'TOPIC_CONSOLIDATION',
  'EVIDENCE_VALIDATION',
  'CONFLICT_ANALYSIS',
  'FINDING_FINALIZATION',
  'REQUIREMENT_GENERATION',
  'VERSION_PLANNING',
  'PRD_GENERATION',
  'TEST_CASE_GENERATION',
  'TRACEABILITY_VALIDATION',
]

function overallProgress(run: AnalysisRun, finalReady: boolean): number {
  if (finalReady || ['COMPLETED_WITH_WARNINGS', 'VALIDATION_FAILED'].includes(run.status)) return 100
  const index = Math.max(0, stageOrder.indexOf(run.current_stage))
  const base = (index / stageOrder.length) * 100
  const next = ((index + 1) / stageOrder.length) * 100
  return Math.min(99, Math.round(base + (next - base) * (run.progress / 100)))
}

export function AnalysisWorkspace({ result }: { result: IngestionResult }) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<WorkspaceTab>('overview')
  const [runView, setRunView] = useState<AnalysisRunView>({
    analysis_run_id: result.analysis_run_id,
    run: result.run,
    provider: result.provider,
    statistics: result.statistics,
    semantic_analysis: null,
    evidence_validation: null,
    product_planning: null,
    final_traceability: null,
    audit_event_count: 0,
  })
  const [topics, setTopics] = useState<TopicCandidate[]>([])
  const [candidates, setCandidates] = useState<FindingCandidatesView['finding_candidates']>([])
  const [findings, setFindings] = useState<FindingsView | null>(null)
  const [planning, setPlanning] = useState<ProductPlanningResult | null>(null)
  const [traceability, setTraceability] = useState<TraceabilityView | null>(null)
  const [pollError, setPollError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    let timer: number | undefined

    const refresh = async () => {
      try {
        const next = await getAnalysisRun(result.analysis_run_id)
        if (disposed) return
        setRunView(next)
        const requests: Promise<void>[] = []
        if (next.semantic_analysis) {
          requests.push(
            Promise.all([getTopics(result.analysis_run_id), getFindingCandidates(result.analysis_run_id)]).then(
              ([topicView, candidateView]) => {
                if (!disposed) {
                  setTopics(topicView.topics)
                  setCandidates(candidateView.finding_candidates)
                }
              },
            ),
          )
        }
        if (next.evidence_validation) {
          requests.push(
            getFindings(result.analysis_run_id).then((value) => {
              if (!disposed) setFindings(value)
            }),
          )
        }
        if (next.product_planning) {
          requests.push(
            getProductPlan(result.analysis_run_id).then((value) => {
              if (!disposed) setPlanning(value.product_planning)
            }),
          )
        }
        if (next.audit_event_count || next.final_traceability) {
          requests.push(
            getTraceability(result.analysis_run_id).then((value) => {
              if (!disposed) setTraceability(value)
            }),
          )
        }
        await Promise.all(requests)
        if (!disposed) setPollError(null)
        const terminal =
          ['FAILED', 'VALIDATION_FAILED'].includes(next.run.status) ||
          (next.final_traceability !== null &&
            ['COMPLETED', 'COMPLETED_WITH_WARNINGS'].includes(next.run.status))
        if (!disposed && !terminal) timer = window.setTimeout(refresh, 1200)
      } catch (error) {
        if (!disposed) {
          setPollError(error instanceof ApiError ? error.message : t('analysis.workspace.errors.poll'))
          timer = window.setTimeout(refresh, 2000)
        }
      }
    }

    void refresh()
    return () => {
      disposed = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [result.analysis_run_id, t])

  const progress = overallProgress(runView.run, Boolean(runView.final_traceability))
  const isRunning = ['PENDING', 'RUNNING'].includes(runView.run.status) ||
    (!runView.final_traceability && !['FAILED', 'VALIDATION_FAILED'].includes(runView.run.status))
  const statusTone = ['FAILED', 'VALIDATION_FAILED'].includes(runView.run.status)
    ? 'bg-[#fff0f0] text-[#9f2f2f]'
    : runView.run.status === 'COMPLETED'
      ? 'bg-[#e9f8f1] text-[#14734f]'
      : 'bg-[#fff7e7] text-[#7a5a16]'

  const counts = useMemo(
    () => ({
      topics: topics.length,
      findings: findings?.findings.length ?? 0,
      requirements: planning?.requirements.length ?? 0,
      versions: planning?.version_plan?.items.length ?? 0,
      tests: planning?.test_cases.length ?? 0,
    }),
    [findings, planning, topics.length],
  )
  const displayErrors = runView.run.error_code
    ? [
        t(`analysis.semantic.errorCodes.${runView.run.error_code}`, {
          defaultValue: runView.run.errors[0] ?? runView.run.error_code,
        }),
        ...runView.run.errors.slice(1),
      ]
    : runView.run.errors

  return (
    <section className="mt-8 border-t border-[#d7e3ee] pt-7" data-testid="analysis-workspace">
      {result.cached_demo?.CACHED_DEMO ? (
        <div
          className="mb-5 rounded-xl border border-[#e2c777] bg-[#fff9e8] px-4 py-3 text-sm text-[#6f5416]"
          data-testid="cached-demo-banner"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <strong>{t('analysis.demo.badge')}</strong>
            <span className="font-mono text-[0.68rem]">{result.cached_demo.model_provider} · {result.cached_demo.model_name}</span>
          </div>
          <p className="mt-1 leading-5">{t('analysis.demo.description')}</p>
          <p className="mt-1 font-mono text-[0.68rem] text-[#806927]">
            {t('analysis.demo.collected')}: {new Date(result.cached_demo.collection_time).toLocaleString()}
            {' · '}{t('analysis.demo.analyzed')}: {new Date(result.cached_demo.analysis_time).toLocaleString()}
          </p>
        </div>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold tracking-[-0.025em] text-[#15314f]">
              {t('analysis.workspace.title')}
            </h2>
            <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusTone}`}>
              {t(`analysis.status.${runView.run.status}`, { defaultValue: runView.run.status })}
            </span>
          </div>
          <p className="mt-1 font-mono text-[0.7rem] text-[#708397]">{result.analysis_run_id}</p>
        </div>
        <div className="text-right text-xs leading-5 text-[#60758b]">
          <p>{runView.run.model_provider ?? t('analysis.workspace.pendingModel')}</p>
          <p>{runView.run.model_name ?? '—'}</p>
        </div>
      </div>

      <div className="mt-5 border-y border-[#d7e3ee] py-4" aria-live="polite">
        <div className="flex items-center justify-between gap-4 text-sm">
          <span className="font-medium text-[#294765]">
            {isRunning
              ? t(`analysis.stages.${runView.run.current_stage}`, { defaultValue: runView.run.current_stage })
              : t('analysis.workspace.progressCompleted')}
          </span>
          <span className="font-mono text-xs text-[#516a82]">{progress}%</span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#dce7f1]">
          <div
            className={`h-full rounded-full ${statusTone.includes('9f2f2f') ? 'bg-[#b84848]' : 'bg-[#175bd8]'}`}
            style={{ width: `${progress}%` }}
          />
        </div>
        {pollError ? <p className="mt-2 text-xs text-[#9f2f2f]">{pollError}</p> : null}
        {runView.run.errors.length ? (
          <div className="mt-3 rounded-xl bg-[#fff0f0] px-4 py-3 text-sm text-[#8e3030]" role="alert">
            <p className="font-semibold">{t('analysis.workspace.pipelineFailed')}</p>
            <ul className="mt-1 list-disc space-y-1 pl-5">
            {displayErrors.map((error) => <li key={error}>{error}</li>)}
            </ul>
          </div>
        ) : null}
      </div>

      <div className="mt-6 min-w-0 lg:grid lg:grid-cols-[13.5rem_minmax(0,1fr)] lg:gap-8">
        <nav
          aria-label={t('analysis.workspace.navigation')}
          className="-mx-4 mb-5 flex gap-1 overflow-x-auto border-y border-[#d7e3ee] bg-[#edf4fa] px-4 py-2 sm:-mx-6 sm:px-6 lg:sticky lg:top-4 lg:mx-0 lg:mb-0 lg:block lg:self-start lg:overflow-visible lg:rounded-xl lg:border lg:p-2"
        >
          {tabs.map((item) => (
            <button
              className={`shrink-0 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-[#175bd8] lg:mb-1 lg:block lg:w-full lg:last:mb-0 ${
                tab === item
                  ? 'bg-white text-[#1556bc] shadow-[0_1px_4px_rgba(20,57,93,0.12)]'
                  : 'text-[#536b83] hover:bg-white/70 hover:text-[#294765]'
              }`}
              data-testid={`workspace-tab-${item}`}
              key={item}
              onClick={() => setTab(item)}
              type="button"
            >
              {t(`analysis.workspace.tabs.${item}`)}
            </button>
          ))}
        </nav>

        <div className="min-w-0">
          <WorkspacePanel
            activeTab={tab}
            candidates={candidates}
            counts={counts}
            findings={findings}
            ingestion={result}
            onNavigate={setTab}
            planning={planning}
            runView={runView}
            topics={topics}
            traceability={traceability}
          />
        </div>
      </div>
    </section>
  )
}
