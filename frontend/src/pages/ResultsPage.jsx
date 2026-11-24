import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client.js'
import AuthImage, { previewRequest } from '../components/AuthImage.jsx'
import { ErrorNote, Loading, Notice, PageHeader, StatusPill } from '../components/ui.jsx'

const PAGE = 12

const RESULT_METRIC_COLORS = {
  'Usable samples': { bg: 'linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%)', border: '#A7F3D0', color: '#047857' },
  'Passed checks': { bg: 'linear-gradient(135deg, #F0FDFA 0%, #CCFBF1 100%)', border: '#99F6E4', color: '#0F766E' },
  'With warnings': { bg: 'linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 100%)', border: '#FDE68A', color: '#B45309' },
  'Rejected by checks': { bg: 'linear-gradient(135deg, #FFF1F2 0%, #FFE4E6 100%)', border: '#FECDD3', color: '#BE123C' },
  'Rejected by you': { bg: 'linear-gradient(135deg, #FEF2F2 0%, #FEE2E2 100%)', border: '#FECACA', color: '#B91C1C' },
}

function SampleCard({ jobId, sample }) {
  const qc = useQueryClient()
  const [slice, setSlice] = useState(null)
  const [open, setOpen] = useState(false)
  const review = useMutation({ mutationFn: (s) => api.reviewSample(jobId, sample.sample_id, s), onSuccess: () => qc.invalidateQueries({ queryKey: ['results', jobId] }) })
  const hasFile = sample.validation_status !== 'rejected'
  const volume = sample.modality !== 'xray'
  const maxSlice = (sample.shape?.[sample.shape.length - 1] ?? 1) - 1
  const params = { slice_index: slice ?? undefined, max_size: 400 }
  const status = sample.review_status === 'rejected' ? 'rejected' : sample.validation_status === 'passed' ? 'passed' : sample.validation_status

  return (
    <li className="panel overflow-hidden border border-slate-200/90 rounded-2xl bg-white shadow-sm transition-all duration-200 hover:shadow-md">
      {hasFile ? (
        <div className="grid grid-cols-2 gap-px bg-slate-950">
          <figure className="relative">
            <AuthImage className="aspect-square" alt="Original" cacheKey={`${sample.source_image_id}-${slice}`} request={previewRequest(sample.source_image_id, params)} />
            <figcaption className="absolute bottom-0 inset-x-0 bg-slate-900/90 backdrop-blur-sm px-2.5 py-1 text-[11px] font-bold text-emerald-400">
              Original
            </figcaption>
          </figure>
          <figure className="relative">
            <AuthImage className="aspect-square" alt="Augmented" cacheKey={`${sample.sample_id}-${slice}`} request={previewRequest(sample.sample_id, params)} />
            <figcaption className="absolute bottom-0 inset-x-0 bg-slate-900/90 backdrop-blur-sm px-2.5 py-1 text-[11px] font-bold text-indigo-300">
              Augmented
            </figcaption>
          </figure>
        </div>
      ) : (
        <p className="bg-red-50 border-b border-red-200 px-4 py-12 text-center text-xs font-bold text-red-600">
          Rejected by technical checks — no output file written.
        </p>
      )}
      {hasFile && volume && (
        <div className="bg-slate-900 px-3 pb-2 pt-1 border-t border-slate-800">
          <input aria-label="Slice" type="range" className="w-full accent-teal-500" min="0" max={maxSlice} value={slice ?? Math.floor(maxSlice / 2)} onChange={(e) => setSlice(Number(e.target.value))} />
        </div>
      )}
      <div className="space-y-2.5 p-4 text-sm">
        <div className="flex items-center justify-between gap-2">
          <span className="font-extrabold text-slate-900">{sample.labels.join(' + ')}</span>
          <StatusPill status={status} />
        </div>
        {sample.validation.messages.length > 0 && (
          <ul className="list-disc pl-4 text-xs font-semibold text-amber-600">
            {sample.validation.messages.map((m) => <li key={m}>{m}</li>)}
          </ul>
        )}
        <p className="text-xs font-medium text-slate-500 truncate" title={sample.transform_history.map((h) => h.name.replace(/_/g, ' ')).join(', ')}>
          Transforms: {sample.transform_history.map((h) => h.name.replace(/_/g, ' ')).join(', ')}
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          {hasFile && sample.review_status !== 'rejected' && (
            <button className="btn-secondary px-2.5 py-1 text-xs text-red-600 hover:bg-red-50" disabled={review.isPending} onClick={() => review.mutate('rejected')}>
              Flag/Reject
            </button>
          )}
          {sample.review_status === 'rejected' && hasFile && (
            <button className="btn-secondary px-2.5 py-1 text-xs text-teal-600 hover:bg-teal-50" disabled={review.isPending} onClick={() => review.mutate('auto')}>
              Restore
            </button>
          )}
          <button className="btn-secondary px-2.5 py-1 text-xs" onClick={() => setOpen(!open)}>
            {open ? 'Hide Provenance' : 'View Provenance'}
          </button>
        </div>
        {open && (
          <pre className="max-h-56 overflow-auto rounded-xl bg-slate-900 text-teal-300 p-3 text-[11px] font-mono leading-tight">
            {JSON.stringify({ source: sample.source_image_id, seed: sample.seed, attempts: sample.attempts, interpolation: sample.interpolation, padding: sample.padding, transforms: sample.transform_history }, null, 1)}
          </pre>
        )}
        <ErrorNote error={review.error} />
      </div>
    </li>
  )
}

export default function ResultsPage() {
  const { jobId } = useParams()
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(0)
  const res = useQuery({ queryKey: ['results', jobId, status, page], queryFn: () => api.results(jobId, { status: status || undefined, skip: page * PAGE, limit: PAGE }), placeholderData: keepPreviousData })

  if (res.isLoading) return <Loading what="Loading review pipeline" />
  if (res.error) return <ErrorNote error={res.error} />
  const r = res.data
  const c = r.counts

  return (
    <>
      <PageHeader
        title="Augmentation Results & Clinical Audit"
        sub="Compare each augmented image against its original counterpart. Automated checks verify geometry and intensity; human review confirms clinical plausibility."
      >
        <Link to={`/jobs/${jobId}`} className="btn-secondary">
          Job Details
        </Link>
        {r.status === 'completed' && (
          <Link to={`/exports?job=${jobId}`} className="btn-primary">
            Export Package →
          </Link>
        )}
      </PageHeader>

      <section className="mb-8 grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="panel p-5 bg-white border border-slate-200 rounded-2xl shadow-sm">
          <h2 className="mb-3 text-base font-bold" style={{ color: '#0F172A' }}>Class Representation Before & After</h2>
          <div role="img" aria-label="Before and after class counts" style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={r.classes} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="#E2E8F0" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#475569', fontWeight: 600 }} interval={0} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: '#475569' }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="original" name="Original" fill="#0D9488" radius={[4, 4, 0, 0]} />
                <Bar dataKey="final" name="Final (Augmented)" fill="#6366F1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <dl className="panel grid h-fit grid-cols-2 gap-3 p-4 bg-white border border-slate-200 rounded-2xl shadow-sm">
          {[['Usable samples', c.usable], ['Passed checks', c.passed], ['With warnings', c.with_warnings], ['Rejected by checks', c.rejected_by_checks], ['Rejected by you', c.rejected_by_user]].map(([k, v]) => {
            const st = RESULT_METRIC_COLORS[k] || { bg: '#F8FAFC', border: '#E2E8F0', color: '#0F172A' }
            return (
              <div key={k} className="rounded-xl p-3" style={{ background: st.bg, border: `1px solid ${st.border}` }}>
                <dt className="text-[10px] font-bold uppercase tracking-wider text-slate-600 truncate">{k}</dt>
                <dd className="mt-1 text-xl font-extrabold" style={{ color: st.color }}>{v}</dd>
              </div>
            )
          })}
        </dl>
      </section>

      <div className="panel mb-8 overflow-hidden border border-slate-200 rounded-2xl bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead>
            <tr style={{ background: '#F8FAFC', borderBottom: '2px solid #E2E8F0' }}>
              <th className="th" style={{ color: '#334155' }}>Class</th>
              <th className="th" style={{ color: '#334155' }}>Original</th>
              <th className="th" style={{ color: '#334155' }}>Target</th>
              <th className="th" style={{ color: '#334155' }}>Generated</th>
              <th className="th" style={{ color: '#334155' }}>Rejected</th>
              <th className="th" style={{ color: '#334155' }}>Final</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {r.classes.map((k) => (
              <tr key={k.label} className="hover:bg-slate-50 transition-colors">
                <td className="td font-bold" style={{ color: '#0D9488' }}>{k.label}</td>
                <td className="td font-semibold text-slate-700">{k.original}</td>
                <td className="td text-slate-500 font-medium">{k.target}</td>
                <td className="td font-bold" style={{ color: '#6366F1' }}>{k.generated}</td>
                <td className="td font-bold text-red-600">{k.rejected}</td>
                <td className="td font-extrabold text-slate-900">{k.final}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {r.validation_messages.length > 0 && (
        <div className="mb-6">
          <Notice tone="warn" title="Quality Control Notifications">
            <ul className="list-disc pl-5 mt-1 space-y-1 font-medium text-slate-700">
              {r.validation_messages.map((m) => (
                <li key={m.message}>
                  {m.message} <span className="font-bold text-amber-900">({m.count} occurrences)</span>
                </li>
              ))}
            </ul>
          </Notice>
        </div>
      )}

      <section>
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-lg font-bold" style={{ color: '#0F172A' }}>
            Generated Samples <span className="text-sm font-normal text-slate-500">({r.total_filtered} matching filter)</span>
          </h2>
          <select aria-label="Filter by check result" className="input w-52 font-semibold" value={status} onChange={(e) => { setStatus(e.target.value); setPage(0) }}>
            <option value="">All validation results</option>
            <option value="passed">Passed only</option>
            <option value="warning">With warnings only</option>
            <option value="rejected">Rejected only</option>
          </select>
        </div>
        <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {r.samples.map((s) => <SampleCard key={s.sample_id} jobId={jobId} sample={s} />)}
        </ul>
        {r.total_filtered > PAGE && (
          <div className="mt-6 flex items-center justify-center gap-3 text-sm">
            <button className="btn-secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>
              ← Previous
            </button>
            <span className="font-semibold text-slate-700">
              Page {page + 1} of {Math.ceil(r.total_filtered / PAGE)}
            </span>
            <button className="btn-secondary" disabled={(page + 1) * PAGE >= r.total_filtered} onClick={() => setPage(page + 1)}>
              Next →
            </button>
          </div>
        )}
      </section>
    </>
  )
}
