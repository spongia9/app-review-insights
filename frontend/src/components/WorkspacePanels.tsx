import { useTranslation } from 'react-i18next'

import { apiBaseUrl } from '../api/client'

import type {
  AnalysisRunView,
  ArtifactValidationStatus,
  FindingCandidate,
  FindingsView,
  IngestionResult,
  ProductPlanningResult,
  Review,
  TopicCandidate,
  TraceabilityView,
} from '../types/analysis'
import type { WorkspaceTab } from './AnalysisWorkspace'

interface WorkspacePanelProps {
  activeTab: WorkspaceTab
  ingestion: IngestionResult
  runView: AnalysisRunView
  topics: TopicCandidate[]
  candidates: FindingCandidate[]
  findings: FindingsView | null
  planning: ProductPlanningResult | null
  traceability: TraceabilityView | null
  counts: { topics: number; findings: number; requirements: number; versions: number; tests: number }
  onNavigate: (tab: WorkspaceTab) => void
}

function SectionHeading({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-5 border-b border-[#d7e3ee] pb-4">
      <h3 className="text-lg font-semibold tracking-[-0.02em] text-[#17314d]">{title}</h3>
      {description ? <p className="mt-1 max-w-[72ch] text-sm leading-6 text-[#64798f]">{description}</p> : null}
    </div>
  )
}

function Percent({ value }: { value: number | null | undefined }) {
  const { i18n, t } = useTranslation()
  if (value === null || value === undefined) return <>{t('analysis.planning.notApplicable')}</>
  return <>{new Intl.NumberFormat(i18n.resolvedLanguage ?? 'zh-CN', { style: 'percent' }).format(value)}</>
}

function ValidationBadge({ value }: { value: ArtifactValidationStatus }) {
  const { t } = useTranslation()
  const tones: Record<ArtifactValidationStatus, string> = {
    ACCEPTED: 'bg-[#e9f8f1] text-[#14734f]',
    REVISED: 'bg-[#fff5df] text-[#7b5711]',
    REJECTED: 'bg-[#fff0f0] text-[#9f2f2f]',
    ASSUMPTION: 'bg-[#f2edff] text-[#6543a2]',
  }
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${tones[value]}`}>
      {t(`artifactValidation.${value}`)}
    </span>
  )
}

function ReviewEvidence({ review, relation, reason }: { review: Review; relation?: string; reason?: string }) {
  const { t } = useTranslation()
  return (
    <div className="border-t border-[#e1eaf2] py-3 first:border-t-0">
      <div className="flex flex-wrap items-center gap-2 text-xs text-[#64798f]">
        <span className="font-mono font-semibold text-[#315473]">{review.id}</span>
        <span>{t('analysis.table.rating')}: {review.rating ?? '—'}</span>
        <span>{t('analysis.table.version')}: {review.version ?? '—'}</span>
        {relation ? <span className="rounded-full bg-[#edf4fa] px-2 py-0.5">{relation}</span> : null}
      </div>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[#38536e]">{review.text}</p>
      {reason ? <p className="mt-2 text-xs leading-5 text-[#687d92]">{reason}</p> : null}
    </div>
  )
}

function EmptyState({ children }: { children: string }) {
  return <p className="rounded-xl bg-[#edf4fa] px-4 py-6 text-center text-sm text-[#667c91]">{children}</p>
}

function OverviewPanel(props: WorkspacePanelProps) {
  const { t } = useTranslation()
  const { ingestion, runView, counts, traceability } = props
  const metrics = [
    ['raw', ingestion.statistics?.raw_review_count ?? 0],
    ['clean', ingestion.statistics?.clean_review_count ?? 0],
    ['topics', counts.topics],
    ['findings', counts.findings],
    ['requirements', counts.requirements],
    ['versions', counts.versions],
    ['tests', counts.tests],
  ] as const
  const final = traceability?.traceability
  return (
    <div data-testid="workspace-overview">
      <SectionHeading title={t('analysis.workspace.overview.title')} description={t('analysis.workspace.overview.description')} />
      <dl className="grid grid-cols-2 overflow-hidden rounded-xl border border-[#d7e3ee] bg-white sm:grid-cols-4 xl:grid-cols-7">
        {metrics.map(([key, value]) => (
          <div className="border-b border-r border-[#e1eaf2] px-4 py-4 last:border-r-0 sm:[&:nth-last-child(-n+3)]:border-b-0 xl:border-b-0" key={key}>
            <dt className="text-xs leading-5 text-[#6b8095]">{t(`analysis.workspace.overview.metrics.${key}`)}</dt>
            <dd className="mt-1 font-mono text-xl font-semibold text-[#17314d]">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,0.65fr)]">
        <dl className="divide-y divide-[#e1eaf2] border-y border-[#d7e3ee] text-sm">
          {[
            ['goal', runView.run.analysis_goal || t('analysis.semantic.noGoal')],
            ['model', `${runView.run.model_provider ?? '—'} / ${runView.run.model_name ?? '—'}`],
            ['language', t(`analysis.outputLanguage.${runView.run.resolved_output_language}`)],
            ['source', `${runView.provider.source}${runView.provider.storefront ? ` · ${runView.provider.storefront.toUpperCase()}` : ''}`],
            ['status', t(`analysis.status.${runView.run.status}`, { defaultValue: runView.run.status })],
          ].map(([key, value]) => (
            <div className="grid gap-1 py-3 sm:grid-cols-[10rem_1fr]" key={key}>
              <dt className="text-[#6b8095]">{t(`analysis.workspace.overview.${key}`)}</dt>
              <dd className="font-medium text-[#294765]">{value}</dd>
            </div>
          ))}
        </dl>
        <div className="rounded-xl bg-[#edf4fa] p-5">
          <p className="text-sm font-semibold text-[#294765]">{t('analysis.workspace.overview.coverage')}</p>
          <p className="mt-2 font-mono text-3xl font-semibold tracking-[-0.03em] text-[#175bd8]">
            <Percent value={final?.coverage.overall_traceability_coverage} />
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
            {[
              ['warnings', final?.coverage.warnings.length ?? runView.run.warnings.length],
              ['assumptions', final?.assumption_count ?? 0],
              ['revisions', final?.revised_count ?? 0],
              ['rejected', final?.rejected_count ?? 0],
            ].map(([key, value]) => (
              <div key={key}>
                <dt className="text-[#6b8095]">{t(`analysis.workspace.overview.${key}`)}</dt>
                <dd className="mt-0.5 font-mono text-base font-semibold text-[#294765]">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  )
}

function ReviewsPanel({ ingestion, traceability, onNavigate }: WorkspacePanelProps) {
  const { t, i18n } = useTranslation()
  const forward = new Map(traceability?.traceability?.forward.map((item) => [item.review_id, item]) ?? [])
  return (
    <div data-testid="workspace-reviews">
      <SectionHeading title={t('analysis.workspace.reviews.title')} description={t('analysis.workspace.reviews.description')} />
      <div className="overflow-x-auto rounded-xl border border-[#d7e3ee] bg-white">
        <table className="w-full min-w-[980px] border-collapse text-left text-sm">
          <thead className="bg-[#edf4fa] text-xs text-[#526a82]">
            <tr>
              {['id', 'rating', 'text', 'version', 'date', 'source', 'related'].map((key) => (
                <th className="border-b border-[#d7e3ee] px-3 py-3 font-semibold" key={key}>{t(`analysis.workspace.reviews.columns.${key}`)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ingestion.reviews.map((review) => {
              const links = forward.get(review.id)
              return (
                <tr className="border-b border-[#e4ecf3] align-top last:border-b-0" key={review.id}>
                  <td className="px-3 py-3 font-mono text-xs font-semibold text-[#315473]">{review.id}</td>
                  <td className="px-3 py-3 font-mono">{review.rating ?? '—'}</td>
                  <td className="max-w-xl px-3 py-3 leading-6 text-[#38536e]">
                    <p className="font-medium text-[#294765]">{review.title ?? '—'}</p>
                    <p className="mt-1 whitespace-pre-wrap">{review.text}</p>
                  </td>
                  <td className="px-3 py-3 font-mono text-xs">{review.version ?? '—'}</td>
                  <td className="px-3 py-3 text-xs">{review.created_at ? new Intl.DateTimeFormat(i18n.resolvedLanguage).format(new Date(review.created_at)) : '—'}</td>
                  <td className="px-3 py-3 text-xs">{review.source}</td>
                  <td className="px-3 py-3 text-xs">
                    {links?.finding_ids.length ? (
                      <button className="font-semibold text-[#175bd8] hover:underline" onClick={() => onNavigate('findings')} type="button">
                        {links.finding_ids.join(', ')}
                      </button>
                    ) : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CleaningPanel({ ingestion }: WorkspacePanelProps) {
  const { t, i18n } = useTranslation()
  const stats = ingestion.statistics
  if (!stats) return <EmptyState>{t('analysis.workspace.pending')}</EmptyState>
  return (
    <div data-testid="workspace-cleaning">
      <SectionHeading title={t('analysis.workspace.cleaning.title')} description={t('analysis.workspace.cleaning.description')} />
      <dl className="grid grid-cols-2 overflow-hidden rounded-xl border border-[#d7e3ee] bg-white sm:grid-cols-5">
        {(['raw_review_count', 'clean_review_count', 'duplicate_count', 'invalid_count'] as const).map((key) => (
          <div className="border-b border-r border-[#e1eaf2] px-4 py-4 sm:border-b-0" key={key}>
            <dt className="text-xs text-[#6b8095]">{t(`analysis.statistics.${key}`)}</dt>
            <dd className="mt-1 font-mono text-xl font-semibold">{stats[key]}</dd>
          </div>
        ))}
        <div className="px-4 py-4">
          <dt className="text-xs text-[#6b8095]">{t('analysis.statistics.retention_rate')}</dt>
          <dd className="mt-1 font-mono text-xl font-semibold"><Percent value={stats.retention_rate} /></dd>
        </div>
      </dl>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div>
          <h4 className="text-sm font-semibold text-[#294765]">{t('analysis.workspace.cleaning.provenance')}</h4>
          <dl className="mt-2 divide-y divide-[#e1eaf2] border-y border-[#d7e3ee] text-sm">
            <div className="flex justify-between gap-4 py-3"><dt>{t('analysis.table.source')}</dt><dd>{ingestion.provider.source}</dd></div>
            <div className="flex justify-between gap-4 py-3"><dt>{t('analysis.results.storefront')}</dt><dd>{ingestion.provider.storefront ?? '—'}</dd></div>
            <div className="flex justify-between gap-4 py-3"><dt>{t('analysis.workspace.cleaning.collectionTime')}</dt><dd>{new Intl.DateTimeFormat(i18n.resolvedLanguage, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(ingestion.provider.collection_time))}</dd></div>
          </dl>
        </div>
        <div>
          <h4 className="text-sm font-semibold text-[#294765]">{t('analysis.results.limitations')}</h4>
          {ingestion.provider.source_limitations.length ? (
            <ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-6 text-[#5c7187]">
              {ingestion.provider.source_limitations.map((item) => <li key={item}>{item}</li>)}
            </ul>
          ) : <p className="mt-2 text-sm text-[#687d92]">{t('analysis.workspace.cleaning.noLimitations')}</p>}
        </div>
      </div>
      {ingestion.rejected_rows.length ? (
        <details className="mt-6 rounded-xl border border-[#d7e3ee] bg-white p-4">
          <summary className="cursor-pointer text-sm font-semibold text-[#294765]">{t('analysis.workspace.cleaning.rejectedRows', { count: ingestion.rejected_rows.length })}</summary>
          <ul className="mt-3 space-y-2 text-sm text-[#60758b]">
            {ingestion.rejected_rows.map((item) => <li key={`${item.row_number}-${item.code}`}>#{item.row_number} · {item.code} · {item.message}</li>)}
          </ul>
        </details>
      ) : null}
    </div>
  )
}

function TopicsPanel({ topics, candidates, ingestion }: WorkspacePanelProps) {
  const { t } = useTranslation()
  const reviewMap = new Map(ingestion.reviews.map((review) => [review.id, review]))
  return (
    <div data-testid="workspace-topics">
      <SectionHeading title={t('analysis.workspace.topics.title')} description={t('analysis.workspace.topics.description')} />
      {!topics.length ? <EmptyState>{t('analysis.workspace.pending')}</EmptyState> : (
        <div className="space-y-3">
          {topics.map((topic) => (
            <details className="rounded-xl border border-[#d7e3ee] bg-white p-4" key={topic.id}>
              <summary className="cursor-pointer list-none">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div><p className="font-semibold text-[#294765]">{topic.name}</p><p className="mt-1 text-sm leading-6 text-[#60758b]">{topic.summary}</p></div>
                  <span className="rounded-full bg-[#edf4fa] px-2.5 py-1 font-mono text-xs text-[#315473]">{topic.review_ids.length}</span>
                </div>
              </summary>
              <div className="mt-4 border-t border-[#e1eaf2] pt-2">
                {topic.review_ids.slice(0, 10).map((id) => reviewMap.get(id) ? <ReviewEvidence key={id} review={reviewMap.get(id) as Review} /> : null)}
              </div>
            </details>
          ))}
        </div>
      )}
      <div className="mt-8">
        <h4 className="text-base font-semibold text-[#294765]">{t('analysis.semantic.findings')}</h4>
        <p className="mt-1 text-xs text-[#687d92]">{t('analysis.workspace.topics.candidateNote')}</p>
        <div className="mt-3 space-y-3">
          {candidates.map((candidate) => (
            <details className="rounded-xl bg-[#edf4fa] p-4" key={candidate.id}>
              <summary className="cursor-pointer list-none">
                <p className="text-xs font-semibold text-[#175bd8]">{candidate.topic}</p>
                <p className="mt-1 font-semibold text-[#294765]">{candidate.title}</p>
                <p className="mt-1 text-sm leading-6 text-[#60758b]">{candidate.problem}</p>
              </summary>
              <p className="mt-3 font-mono text-xs text-[#60758b]">{candidate.supporting_review_ids.join(', ')}</p>
            </details>
          ))}
        </div>
      </div>
    </div>
  )
}

function FindingsPanel({ findings, ingestion, planning }: WorkspacePanelProps) {
  const { t, i18n } = useTranslation()
  if (!findings) return <EmptyState>{t('analysis.workspace.pending')}</EmptyState>
  const reviewMap = new Map(ingestion.reviews.map((review) => [review.id, review]))
  const auditMap = new Map(findings.audits.map((audit) => [audit.finding_candidate_id, audit]))
  const requirements = planning?.requirements ?? []
  return (
    <div data-testid="workspace-findings">
      <SectionHeading title={t('analysis.workspace.findings.title')} description={t('analysis.workspace.findings.description')} />
      <div className="space-y-4">
        {findings.findings.map((finding) => {
          const audit = auditMap.get(finding.validation_metadata.finding_candidate_id)
          const relatedRequirements = requirements.filter((item) => item.finding_ids.includes(finding.id))
          return (
            <article className="rounded-xl border border-[#d7e3ee] bg-white p-5" key={finding.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0"><p className="text-xs font-semibold text-[#175bd8]">{finding.topic} · {finding.id}</p><h4 className="mt-1 text-base font-semibold text-[#294765]">{finding.title}</h4><p className="mt-2 max-w-[72ch] text-sm leading-6 text-[#526a82]">{finding.problem}</p></div>
                <span className="rounded-full bg-[#edf4fa] px-2.5 py-1 text-xs font-semibold text-[#315473]">{t(`findingStatus.${finding.status}`)}</span>
              </div>
              <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-y border-[#e1eaf2] py-3 text-xs">
                <div><dt className="text-[#6b8095]">{t('terms.supportingEvidence')}</dt><dd className="mt-0.5 font-mono font-semibold">{finding.support_count}</dd></div>
                <div><dt className="text-[#6b8095]">{t('terms.conflictingEvidence')}</dt><dd className="mt-0.5 font-mono font-semibold">{finding.conflict_count}</dd></div>
                <div><dt className="text-[#6b8095]">{t('terms.evidenceStrength')}</dt><dd className="mt-0.5 font-semibold">{t(`analysis.evidence.strength.${finding.evidence_strength}`)}</dd></div>
                <div><dt className="text-[#6b8095]">{t('terms.confidence')}</dt><dd className="mt-0.5 font-mono font-semibold">{new Intl.NumberFormat(i18n.resolvedLanguage, { style: 'percent' }).format(finding.confidence)}</dd></div>
              </dl>
              <div className="mt-4 grid gap-3 text-sm leading-6 lg:grid-cols-2">
                <div><p className="font-semibold text-[#294765]">{t('analysis.evidence.uncertainty')}</p><p className="mt-1 text-[#60758b]">{finding.uncertainty}</p></div>
                <div><p className="font-semibold text-[#294765]">{t('analysis.evidence.limitations')}</p><ul className="mt-1 list-disc pl-5 text-[#60758b]">{finding.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div>
              </div>
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                {(['SUPPORTS', 'CONFLICTS'] as const).map((stance) => {
                  const ids = stance === 'SUPPORTS' ? finding.supporting_review_ids : finding.conflicting_review_ids
                  return (
                    <details className="rounded-xl bg-[#edf4fa] p-4" key={stance}>
                      <summary className="cursor-pointer text-sm font-semibold text-[#294765]">{t(stance === 'SUPPORTS' ? 'analysis.evidence.view.supporting' : 'analysis.evidence.view.conflicting', { count: ids.length })}</summary>
                      <div className="mt-2">{ids.map((id) => {
                        const review = reviewMap.get(id)
                        const judgment = audit?.judgments.find((item) => item.review_id === id)
                        return review ? <ReviewEvidence key={id} review={review} relation={judgment ? t(`analysis.evidence.stance.${judgment.stance}`) : undefined} reason={judgment?.reason} /> : null
                      })}</div>
                    </details>
                  )
                })}
              </div>
              {relatedRequirements.length ? <p className="mt-4 text-xs text-[#60758b]">{t('analysis.workspace.findings.generatedRequirements')}: <span className="font-mono font-semibold">{relatedRequirements.map((item) => item.id).join(', ')}</span></p> : null}
            </article>
          )
        })}
      </div>
    </div>
  )
}

function RequirementsPanel({ planning, findings, ingestion, onNavigate }: WorkspacePanelProps) {
  const { t } = useTranslation()
  if (!planning) return <EmptyState>{t('analysis.workspace.pending')}</EmptyState>
  const findingMap = new Map(findings?.findings.map((item) => [item.id, item]) ?? [])
  const reviewMap = new Map(ingestion.reviews.map((item) => [item.id, item]))
  return (
    <div data-testid="workspace-requirements">
      <SectionHeading title={t('analysis.workspace.requirements.title')} description={t('analysis.workspace.requirements.description')} />
      <div className="space-y-4">
        {planning.requirements.map((requirement) => (
          <article className="rounded-xl border border-[#d7e3ee] bg-white p-5" key={requirement.id}>
            <div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-[#175bd8] px-2.5 py-1 font-mono text-xs font-semibold text-white">{requirement.final_priority}</span><ValidationBadge value={requirement.validation_result} /><span className="font-mono text-xs text-[#657a90]">{requirement.id}</span></div>
            <h4 className="mt-3 text-base font-semibold text-[#294765]">{requirement.title}</h4>
            <p className="mt-1 text-sm leading-6 text-[#526a82]">{requirement.user_problem}</p>
            <div className="mt-4"><p className="text-sm font-semibold text-[#294765]">{t('analysis.planning.acceptanceCriteria')}</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-[#526a82]">{requirement.acceptance_criteria.map((item) => <li key={item}>{item}</li>)}</ul></div>
            <div className="mt-4 flex flex-wrap gap-2 text-xs text-[#5d7389]"><span>{t('analysis.workspace.requirements.evidenceCount', { count: requirement.review_ids.length })}</span><span>·</span><span>{t('analysis.workspace.requirements.targetVersion')}: {requirement.target_version ?? '—'}</span></div>
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <details className="rounded-xl bg-[#edf4fa] p-4"><summary className="cursor-pointer text-sm font-semibold">{t('analysis.planning.requirements.viewFindings', { count: requirement.finding_ids.length })}</summary><div className="mt-3 space-y-3">{requirement.finding_ids.map((id) => { const item = findingMap.get(id); return item ? <div key={id}><p className="font-mono text-xs text-[#175bd8]">{id}</p><p className="mt-1 text-sm font-medium">{item.title}</p></div> : null })}</div><button className="mt-3 text-xs font-semibold text-[#175bd8]" onClick={() => onNavigate('findings')} type="button">{t('analysis.workspace.openSection')}</button></details>
              <details className="rounded-xl bg-[#edf4fa] p-4"><summary className="cursor-pointer text-sm font-semibold">{t('analysis.planning.requirements.viewReviews', { count: requirement.review_ids.length })}</summary><div className="mt-2">{requirement.review_ids.slice(0, 12).map((id) => reviewMap.get(id) ? <ReviewEvidence key={id} review={reviewMap.get(id) as Review} /> : null)}</div></details>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

function VersionsPanel({ planning }: WorkspacePanelProps) {
  const { t } = useTranslation()
  const plan = planning?.version_plan
  if (!plan) return <EmptyState>{t('analysis.workspace.pending')}</EmptyState>
  return (
    <div data-testid="workspace-versions">
      <SectionHeading title={t('analysis.workspace.versions.title')} description={plan.summary} />
      <div className="space-y-4">{plan.items.map((item) => <article className="rounded-xl border border-[#d7e3ee] bg-white p-5" key={item.id}><div className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm font-semibold text-[#175bd8]">{item.version}</span><ValidationBadge value={item.validation_result} /></div><h4 className="mt-2 text-base font-semibold text-[#294765]">{item.theme}</h4><p className="mt-1 text-sm leading-6 text-[#526a82]">{item.goal}</p><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="font-semibold text-[#294765]">{t('analysis.planning.versionPlan.rationale')}</dt><dd className="mt-1 text-[#60758b]">{item.rationale}</dd></div><div><dt className="font-semibold text-[#294765]">{t('analysis.workspace.versions.risk')}</dt><dd className="mt-1 text-[#60758b]">{item.risk}</dd></div><div><dt className="font-semibold text-[#294765]">{t('analysis.workspace.versions.dependencies')}</dt><dd className="mt-1 text-[#60758b]">{item.dependencies.join(', ') || '—'}</dd></div><div><dt className="font-semibold text-[#294765]">{t('terms.requirement')}</dt><dd className="mt-1 font-mono text-xs text-[#60758b]">{item.requirement_ids.join(', ')}</dd></div></dl></article>)}</div>
    </div>
  )
}

function PrdPanel({ planning }: WorkspacePanelProps) {
  const { t } = useTranslation()
  const artifact = planning?.prd_artifact
  if (!artifact) return <EmptyState>{t('analysis.workspace.pending')}</EmptyState>
  const structured = artifact.structured_prd
  return (
    <div data-testid="workspace-prd">
      <SectionHeading title={t('analysis.workspace.prd.title')} description={t('analysis.workspace.prd.description')} />
      <div className="flex flex-wrap items-center gap-2"><ValidationBadge value={artifact.validation_result} /><a className="rounded-lg bg-[#175bd8] px-3 py-2 text-sm font-semibold text-white hover:bg-[#104ebd]" href={`${apiBaseUrl}/api/analysis/${artifact.analysis_run_id}/product-plan/prd.md`}>{t('analysis.planning.prd.download')}</a></div>
      <article className="mt-5 rounded-xl border border-[#d7e3ee] bg-white p-5 sm:p-6">
        <h4 className="text-xl font-semibold text-[#17314d]">{structured.title}</h4>
        <p className="mt-3 text-sm leading-7 text-[#526a82]">{structured.product_goal}</p>
        <div className="mt-5 grid gap-5 lg:grid-cols-2"><div><h5 className="text-sm font-semibold">{t('analysis.planning.prd.background')}</h5><p className="mt-1 text-sm leading-6 text-[#60758b]">{structured.background}</p></div><div><h5 className="text-sm font-semibold">{t('analysis.planning.prd.scope')}</h5><p className="mt-1 text-sm leading-6 text-[#60758b]">{structured.analysis_scope}</p></div></div>
        <details className="mt-5 border-t border-[#e1eaf2] pt-4"><summary className="cursor-pointer text-sm font-semibold text-[#294765]">{t('analysis.workspace.prd.structured')}</summary><pre className="mt-3 max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-xl bg-[#edf4fa] p-4 text-xs leading-6 text-[#38536e]">{JSON.stringify(structured, null, 2)}</pre></details>
        <details className="mt-4 border-t border-[#e1eaf2] pt-4" open><summary className="cursor-pointer text-sm font-semibold text-[#294765]">{t('analysis.planning.prd.viewMarkdown')}</summary><pre className="mt-3 overflow-x-auto whitespace-pre-wrap font-sans text-sm leading-7 text-[#38536e]">{artifact.rendered_markdown}</pre></details>
      </article>
    </div>
  )
}

function TestsPanel({ planning, findings, ingestion, onNavigate }: WorkspacePanelProps) {
  const { t } = useTranslation()
  if (!planning) return <EmptyState>{t('analysis.workspace.pending')}</EmptyState>
  const requirementMap = new Map(planning.requirements.map((item) => [item.id, item]))
  const findingMap = new Map(findings?.findings.map((item) => [item.id, item]) ?? [])
  const reviewMap = new Map(ingestion.reviews.map((item) => [item.id, item]))
  return (
    <div data-testid="workspace-tests">
      <SectionHeading title={t('analysis.workspace.tests.title')} description={t('analysis.workspace.tests.description')} />
      <div className="space-y-4">{planning.test_cases.map((testCase) => { const requirement = requirementMap.get(testCase.requirement_id); return <article className="rounded-xl border border-[#d7e3ee] bg-white p-5" key={testCase.id}><div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs font-semibold text-[#175bd8]">{testCase.id}</span><span className="rounded-full bg-[#edf4fa] px-2 py-1 text-xs">{testCase.test_type}</span><span className="rounded-full bg-[#edf4fa] px-2 py-1 text-xs">{testCase.priority}</span><ValidationBadge value={testCase.validation_result} /></div><h4 className="mt-3 font-semibold text-[#294765]">{testCase.title}</h4><p className="mt-2 text-sm text-[#60758b]">{t('analysis.planning.testCases.requirement')}: <button className="font-semibold text-[#175bd8]" onClick={() => onNavigate('requirements')} type="button">{requirement?.title ?? testCase.requirement_id}</button></p><div className="mt-4 grid gap-4 lg:grid-cols-2"><div><p className="text-sm font-semibold">{t('analysis.workspace.tests.steps')}</p><ol className="mt-2 list-decimal space-y-1 pl-5 text-sm leading-6 text-[#526a82]">{testCase.steps.map((step) => <li key={step}>{step}</li>)}</ol></div><div><p className="text-sm font-semibold">{t('analysis.planning.testCases.expected')}</p><p className="mt-2 text-sm leading-6 text-[#526a82]">{testCase.expected_result}</p></div></div><details className="mt-4 rounded-xl bg-[#edf4fa] p-4"><summary className="cursor-pointer text-sm font-semibold">{t('analysis.workspace.tests.why')}</summary>{requirement ? <div className="mt-3"><p className="text-sm font-medium">{requirement.title}</p><p className="mt-2 font-mono text-xs text-[#60758b]">{requirement.finding_ids.join(', ')}</p>{requirement.finding_ids.map((id) => findingMap.get(id) ? <p className="mt-2 text-sm text-[#526a82]" key={id}>{findingMap.get(id)?.problem}</p> : null)}<div className="mt-3">{testCase.source_review_ids.slice(0, 8).map((id) => reviewMap.get(id) ? <ReviewEvidence key={id} review={reviewMap.get(id) as Review} /> : null)}</div></div> : null}</details></article> })}</div>
    </div>
  )
}

function TraceabilityPanel({ traceability, onNavigate }: WorkspacePanelProps) {
  const { t } = useTranslation()
  const trace = traceability?.traceability
  if (!trace) return <EmptyState>{t('analysis.workspace.pending')}</EmptyState>
  const coverage = [
    ['overall', trace.coverage.overall_traceability_coverage],
    ['finding', trace.coverage.finding_evidence_coverage],
    ['requirement', trace.coverage.requirement_traceability_coverage],
    ['test', trace.coverage.test_case_traceability_coverage],
  ] as const
  return (
    <div data-testid="workspace-traceability">
      <SectionHeading title={t('analysis.workspace.traceability.title')} description={t('analysis.workspace.traceability.description')} />
      <dl className="grid grid-cols-2 overflow-hidden rounded-xl border border-[#d7e3ee] bg-white xl:grid-cols-4">{coverage.map(([key, value]) => <div className="border-b border-r border-[#e1eaf2] px-4 py-4 xl:border-b-0" key={key}><dt className="text-xs text-[#6b8095]">{t(`analysis.workspace.traceability.coverage.${key}`)}</dt><dd className="mt-1 font-mono text-xl font-semibold text-[#17314d]"><Percent value={value} /></dd></div>)}</dl>
      <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">{(['unsupported_count', 'assumption_count', 'revised_count', 'rejected_count'] as const).map((key) => <div className="flex gap-2" key={key}><dt className="text-[#6b8095]">{t(`analysis.workspace.traceability.counts.${key}`)}</dt><dd className="font-mono font-semibold">{trace[key]}</dd></div>)}</dl>
      {trace.coverage.hard_failures.length ? <div className="mt-5 rounded-xl bg-[#fff0f0] p-4 text-sm text-[#8e3030]"><p className="font-semibold">{t('analysis.workspace.traceability.hardFailures')}</p><ul className="mt-2 list-disc pl-5">{trace.coverage.hard_failures.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
      <div className="mt-6 overflow-x-auto rounded-xl border border-[#d7e3ee] bg-white">
        <table className="w-full min-w-[1100px] border-collapse text-left text-xs">
          <thead className="bg-[#edf4fa] text-[#526a82]"><tr>{['review', 'role', 'finding', 'requirement', 'version', 'test'].map((key) => <th className="border-b border-[#d7e3ee] px-3 py-3 font-semibold" key={key}>{t(`analysis.workspace.traceability.matrix.${key}`)}</th>)}</tr></thead>
          <tbody>{trace.matrix.map((row, index) => <tr className="border-b border-[#e4ecf3] last:border-b-0" key={`${row.review_id}-${row.finding_id}-${row.requirement_id}-${row.test_case_id}-${index}`}><td className="px-3 py-3 font-mono">{row.review_id ?? '—'}</td><td className="px-3 py-3">{row.evidence_role ? t(`analysis.workspace.traceability.roles.${row.evidence_role}`) : '—'}</td><td className="px-3 py-3">{row.finding_id ? <button className="font-mono font-semibold text-[#175bd8]" onClick={() => onNavigate('findings')} type="button">{row.finding_id}</button> : '—'}</td><td className="px-3 py-3">{row.requirement_id ? <button className="font-mono font-semibold text-[#175bd8]" onClick={() => onNavigate('requirements')} type="button">{row.requirement_id}</button> : '—'}</td><td className="px-3 py-3 font-mono">{row.version ?? '—'}</td><td className="px-3 py-3">{row.test_case_id ? <button className="font-mono font-semibold text-[#175bd8]" onClick={() => onNavigate('tests')} type="button">{row.test_case_id}</button> : '—'}</td></tr>)}</tbody>
        </table>
      </div>
    </div>
  )
}

function AuditPanel({ traceability, runView }: WorkspacePanelProps) {
  const { t, i18n } = useTranslation()
  const events = traceability?.audit_events ?? []
  return (
    <div data-testid="workspace-audit">
      <SectionHeading title={t('analysis.workspace.audit.title')} description={t('analysis.workspace.audit.description')} />
      {events.length ? <ol className="border-l border-[#cbd9e7] pl-5">{events.map((event) => <li className="relative pb-5 last:pb-0" key={event.id}><span className={`absolute -left-[1.48rem] top-1.5 size-2.5 rounded-full ${event.event_type === 'ERROR' || event.event_type === 'REJECTION' ? 'bg-[#b84848]' : event.event_type === 'WARNING' || event.event_type === 'REVISION' ? 'bg-[#c18a22]' : 'bg-[#175bd8]'}`} /><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-[#edf4fa] px-2 py-0.5 text-[0.68rem] font-semibold text-[#526a82]">{t(`analysis.workspace.audit.types.${event.event_type}`)}</span><span className="font-mono text-[0.68rem] text-[#6b8095]">{event.stage}</span><time className="text-[0.68rem] text-[#7d8fa1]">{new Intl.DateTimeFormat(i18n.resolvedLanguage, { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(event.created_at))}</time></div><p className="mt-1 text-sm leading-6 text-[#38536e]">{event.message}</p>{event.artifact_id ? <p className="mt-1 font-mono text-xs text-[#6b8095]">{event.artifact_type} · {event.artifact_id}</p> : null}</li>)}</ol> : <EmptyState>{t('analysis.workspace.pending')}</EmptyState>}
      {runView.run.revisions.length ? <details className="mt-6 rounded-xl border border-[#d7e3ee] bg-white p-4"><summary className="cursor-pointer text-sm font-semibold">{t('analysis.workspace.audit.revisions')}</summary><ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-[#60758b]">{runView.run.revisions.map((item) => <li key={item}>{item}</li>)}</ul></details> : null}
    </div>
  )
}

export function WorkspacePanel(props: WorkspacePanelProps) {
  switch (props.activeTab) {
    case 'overview': return <OverviewPanel {...props} />
    case 'reviews': return <ReviewsPanel {...props} />
    case 'cleaning': return <CleaningPanel {...props} />
    case 'topics': return <TopicsPanel {...props} />
    case 'findings': return <FindingsPanel {...props} />
    case 'requirements': return <RequirementsPanel {...props} />
    case 'versions': return <VersionsPanel {...props} />
    case 'prd': return <PrdPanel {...props} />
    case 'tests': return <TestsPanel {...props} />
    case 'traceability': return <TraceabilityPanel {...props} />
    case 'audit': return <AuditPanel {...props} />
  }
}
