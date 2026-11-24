import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client.js'
import { ErrorNote, Loading, Notice, PageHeader, ProgressBar, StatusPill, fmtDate } from '../components/ui.jsx'

const TERMINAL = ['completed', 'failed', 'cancelled']

const METRICS_STYLES = {
  'Planned': { bg: 'linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%)', border: '#C7D2FE', color: '#4338CA', label: '#475569' },
  'Passed checks': { bg: 'linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%)', border: '#A7F3D0', color: '#047857', label: '#475569' },
  'With warnings': { bg: 'linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 100%)', border: '#FDE68A', color: '#B45309', label: '#475569' },
  'Rejected by checks': { bg: 'linear-gradient(135deg, #FFF1F2 0%, #FFE4E6 100%)', border: '#FECDD3', color: '#BE123C', label: '#475569' },
  'Errors': { bg: 'linear-gradient(135deg, #FEF2F2 0%, #FEE2E2 100%)', border: '#FECACA', color: '#B91C1C', label: '#475569' },
}

export default function JobPage() {
  const { jobId } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const job = useQuery({ queryKey: ['job', jobId], queryFn: () => api.job(jobId), refetchInterval: (q) => (q.state.data && TERMINAL.includes(q.state.data.status) ? false : 1500) })
  const cancel = useMutation({ mutationFn: () => api.cancelJob(jobId), onSuccess: () => qc.invalidateQueries({ queryKey: ['job', jobId] }) })
  const del = useMutation({
    mutationFn: () => api.deleteJob(jobId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] })
      nav('/jobs')
    },
  })

  if (job.isLoading) return <Loading what="Loading job details" />
  if (job.error) return <ErrorNote error={job.error} />
  const j = job.data
  const p = j.progress
  const active = !TERMINAL.includes(j.status)

  return (
    <>
      <PageHeader title={j.name} sub={`Seed ${j.seed} · Created ${fmtDate(j.created_at)}`}>
        <StatusPill status={j.status} />
        {active && (
          <button className="btn-secondary" disabled={cancel.isPending || j.cancel_requested} onClick={() => cancel.mutate()}>
            {j.cancel_requested ? 'Cancelling…' : 'Cancel Job'}
          </button>
        )}
        {j.status === 'completed' && (
          <Link to={`/jobs/${jobId}/results`} className="btn-primary">
            Review Results →
          </Link>
        )}
        <button
          className="btn-danger"
          disabled={del.isPending || active}
          title={active ? 'Cancel the running job before deleting' : 'Delete this job'}
          onClick={() => {
            if (window.confirm('Delete this job and all its generated samples permanently?')) {
              del.mutate()
            }
          }}
        >
          {del.isPending ? 'Deleting…' : 'Delete Job'}
        </button>
      </PageHeader>
      <ErrorNote error={cancel.error || del.error} />
      {j.error && <div className="mb-6"><Notice tone="bad" title="Job failed">{j.error}</Notice></div>}
      {j.status === 'cancelled' && <div className="mb-6"><Notice tone="warn">Cancelled. Samples generated before cancelling are kept in the results but the job cannot be exported.</Notice></div>}

      <section className="panel mb-8 p-6 bg-white border border-slate-200 shadow-sm rounded-2xl">
        <ProgressBar percent={p.percent} label="Pipeline Execution" />
        <dl className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-5">
          {[
            ['Planned', p.total],
            ['Passed checks', p.accepted],
            ['With warnings', p.warnings],
            ['Rejected by checks', p.rejected],
            ['Errors', p.failed],
          ].map(([k, v]) => {
            const s = METRICS_STYLES[k] || { bg: '#F8FAFC', border: '#E2E8F0', color: '#0F172A', label: '#64748B' }
            return (
              <div
                key={k}
                className="rounded-xl p-4 shadow-sm transition-transform hover:scale-[1.02]"
                style={{ background: s.bg, border: `1px solid ${s.border}` }}
              >
                <dt className="text-xs font-bold uppercase tracking-wider" style={{ color: s.label }}>{k}</dt>
                <dd className="mt-2 text-2xl font-extrabold" style={{ color: s.color }}>{v.toLocaleString()}</dd>
              </div>
            )
          })}
        </dl>
        {p.rejected > 0 && (
          <p className="mt-4 text-xs font-medium" style={{ color: '#64748B' }}>
            Rejected outputs are retried with a fresh random draw up to 3 times; they are never written to disk.
          </p>
        )}
      </section>

      {j.summary?.errors?.length > 0 && (
        <div className="mb-6">
          <Notice tone="warn" title="Some samples could not be produced">
            <ul className="list-disc pl-5 mt-1 space-y-1 font-medium text-slate-700">
              {j.summary.errors.slice(0, 5).map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </Notice>
        </div>
      )}

      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold" style={{ color: '#0F172A' }}>Execution Log</h2>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-md bg-slate-100 text-slate-600">
            {j.logs.length} events
          </span>
        </div>
        <ol className="panel max-h-96 overflow-y-auto divide-y divide-slate-100 text-sm rounded-2xl border border-slate-200 bg-white shadow-sm">
          {[...j.logs].reverse().map((l, i) => (
            <li key={i} className="flex flex-col sm:flex-row gap-2 sm:gap-4 px-5 py-3 hover:bg-slate-50 transition-colors">
              <span className="w-44 shrink-0 font-mono text-xs font-semibold" style={{ color: '#0D9488' }}>
                {fmtDate(l.t)}
              </span>
              <span className="font-medium text-slate-800">{l.msg}</span>
            </li>
          ))}
        </ol>
      </section>
    </>
  )
}
