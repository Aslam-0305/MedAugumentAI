import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api, downloadExport } from '../api/client.js'
import { Empty, ErrorNote, Field, Loading, PageHeader, StatusPill, fmtDate } from '../components/ui.jsx'

const mb = (b) => (b ? `${(b / 2 ** 20).toFixed(1)} MB` : '—')

export default function ExportsPage() {
  const [params] = useSearchParams()
  const qc = useQueryClient()
  const [jobId, setJobId] = useState(params.get('job') || '')
  const [opts, setOpts] = useState({ include_originals: true, include_validation_test: true, include_warnings: true })
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api.jobs() })
  const exportsQ = useQuery({ queryKey: ['exports'], queryFn: api.exports, refetchInterval: (q) => (q.state.data?.some((e) => ['queued', 'running'].includes(e.status)) ? 1500 : false) })
  const create = useMutation({ mutationFn: () => api.createExport({ job_id: jobId, ...opts }), onSuccess: () => qc.invalidateQueries({ queryKey: ['exports'] }) })
  const dl = useMutation({ mutationFn: (e) => downloadExport(e.export_id, `medaugment_export_${e.export_id}.zip`) })
  const completed = (jobs.data || []).filter((j) => j.status === 'completed')
  const check = (k, label, hint) => (
    <label className="flex items-start gap-3 text-sm cursor-pointer p-3 rounded-xl bg-slate-50 border border-slate-200 hover:bg-teal-50/40 transition-colors">
      <input type="checkbox" className="mt-1 h-4 w-4 rounded text-teal-600 focus:ring-teal-500" checked={opts[k]} onChange={(e) => setOpts({ ...opts, [k]: e.target.checked })} />
      <div>
        <span className="font-bold text-slate-800">{label}</span>
        <span className="block text-xs font-medium text-slate-500 mt-0.5">{hint}</span>
      </div>
    </label>
  )

  return (
    <>
      <PageHeader
        title="Dataset Exports"
        sub="A ZIP package containing images, masks, labels, manifest with SHA-256 checksums, full transform provenance, and a summary audit report."
      />
      <section className="panel mb-10 max-w-2xl space-y-5 p-8 bg-white border border-slate-200 shadow-sm rounded-2xl">
        <Field label="Completed Augmentation Job">
          <select className="input font-semibold" style={{ color: '#0F172A' }} value={jobId} onChange={(e) => setJobId(e.target.value)}>
            <option value="">Choose a completed job…</option>
            {completed.map((j) => (
              <option key={j.job_id} value={j.job_id}>{j.name} · {fmtDate(j.created_at)}</option>
            ))}
          </select>
        </Field>
        
        <div className="space-y-3">
          {check('include_originals', 'Include original training images', 'Copied byte-for-byte, so the export is a complete standalone training set.')}
          {check('include_validation_test', 'Include validation & test splits', 'Untouched originals, kept in separate folders to ensure zero data leakage.')}
          {check('include_warnings', 'Include samples with warnings', 'Samples flagged with non-critical warnings. Manually rejected samples are always excluded.')}
        </div>

        <ErrorNote error={create.error} />
        
        <div className="pt-2">
          <button className="btn-primary" disabled={!jobId || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? 'Generating Export ZIP…' : 'Generate Dataset Export'}
          </button>
        </div>
      </section>

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold" style={{ color: '#0F172A' }}>Export History</h2>
      </div>
      <ErrorNote error={dl.error} />
      {exportsQ.isLoading ? <Loading what="Loading export packages" /> : !exportsQ.data?.length ? (
        <Empty title="No export packages yet" />
      ) : (
        <div className="panel overflow-hidden border border-slate-200 shadow-sm rounded-2xl bg-white">
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr style={{ background: 'linear-gradient(to right, #F8FAFC, #F1F5F9)', borderBottom: '2px solid #E2E8F0' }}>
                  <th className="th" style={{ color: '#334155', fontWeight: 700 }}>Created</th>
                  <th className="th" style={{ color: '#334155', fontWeight: 700 }}>Job ID</th>
                  <th className="th" style={{ color: '#334155', fontWeight: 700 }}>Files</th>
                  <th className="th" style={{ color: '#334155', fontWeight: 700 }}>Size</th>
                  <th className="th" style={{ color: '#334155', fontWeight: 700 }}>Status</th>
                  <th className="th" style={{ color: '#334155', fontWeight: 700 }}>Download</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {exportsQ.data.map((e) => (
                  <tr
                    key={e.export_id}
                    className="transition-colors hover:bg-slate-50"
                  >
                    <td className="td text-xs font-semibold text-slate-700">{fmtDate(e.created_at)}</td>
                    <td className="td font-mono text-xs text-slate-500">{e.job_id}</td>
                    <td className="td font-bold" style={{ color: '#0D9488' }}>{e.n_files?.toLocaleString() ?? '—'}</td>
                    <td className="td font-semibold text-slate-700">{mb(e.size_bytes)}</td>
                    <td className="td">
                      <StatusPill status={e.status} />
                      {e.error && <p className="mt-1 max-w-xs text-xs font-semibold text-red-600">{e.error}</p>}
                    </td>
                    <td className="td">
                      {e.status === 'completed' && (
                        <button
                          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold text-white shadow-sm transition-transform hover:scale-105"
                          style={{ background: 'linear-gradient(135deg, #0D9488, #4F46E5)' }}
                          disabled={dl.isPending}
                          onClick={() => dl.mutate(e)}
                        >
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                          </svg>
                          Download ZIP
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}
