import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client.js'
import AuthImage, { previewRequest } from '../components/AuthImage.jsx'
import { ErrorNote, Field, Loading, MODALITY, Notice, PageHeader, StatusPill } from '../components/ui.jsx'
import DistributionChart from '../features/analysis/DistributionChart.jsx'

const PAGE = 24

export default function DatasetPage() {
  const { datasetId } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [label, setLabel] = useState('')
  const [split, setSplit] = useState('')
  const [page, setPage] = useState(0)
  const [ratios, setRatios] = useState({ train: 0.7, val: 0.15, test: 0.15 })
  const [seed, setSeed] = useState(42)

  const ds = useQuery({ queryKey: ['dataset', datasetId], queryFn: () => api.dataset(datasetId) })
  const stats = useQuery({ queryKey: ['stats', datasetId, ds.data?.splits_defined], queryFn: () => api.statistics(datasetId), enabled: !!ds.data && ds.data.status !== 'failed' })
  const images = useQuery({
    queryKey: ['images', datasetId, label, split, page],
    queryFn: () => api.images(datasetId, { label: label || undefined, split: split || undefined, status: 'valid', skip: page * PAGE, limit: PAGE }),
    enabled: !!ds.data, placeholderData: keepPreviousData,
  })
  const splitMut = useMutation({
    mutationFn: (body) => api.createSplits(datasetId, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['dataset', datasetId] }); qc.invalidateQueries({ queryKey: ['stats', datasetId] }); qc.invalidateQueries({ queryKey: ['images', datasetId] }) },
  })
  const del = useMutation({ mutationFn: () => api.deleteDataset(datasetId), onSuccess: () => { qc.invalidateQueries({ queryKey: ['datasets'] }); nav('/') } })

  if (ds.isLoading) return <Loading what="Loading dataset" />
  if (ds.error) return <ErrorNote error={ds.error} />
  const d = ds.data
  const s = stats.data
  const ratioSum = Object.values(ratios).reduce((a, b) => a + Number(b), 0)

  return (
    <>
      <PageHeader
        title={d.name}
        sub={`${MODALITY[d.modality]} · ${d.annotation_type === 'multilabel' ? 'Multi-label' : 'Single-label'} · ${d.counts.valid.toLocaleString()} valid images from ${d.counts.patients.toLocaleString()} subjects`}
      >
        <StatusPill status={d.status} />
        {d.status !== 'failed' && (
          <Link to={`/datasets/${datasetId}/augment`} className="btn-primary">
            Plan Augmentation →
          </Link>
        )}
        <button
          className="btn-danger"
          onClick={() => window.confirm('Delete this dataset and all associated jobs and exports?') && del.mutate()}
        >
          Delete
        </button>
      </PageHeader>
      <ErrorNote error={del.error} />

      {d.validation.errors + d.validation.warnings > 0 && (
        <details className="mb-6 rounded-2xl border border-amber-200 bg-amber-50/50 p-4" open={d.status !== 'ready'}>
          <summary className="cursor-pointer text-sm font-bold text-amber-800">
            Validation Issues: {d.validation.errors} error{d.validation.errors === 1 ? '' : 's'}, {d.validation.warnings} warning{d.validation.warnings === 1 ? '' : 's'}
            {d.counts.invalid > 0 && ` — ${d.counts.invalid} image(s) excluded`}
          </summary>
          <ul className="panel mt-3 divide-y divide-slate-100 text-sm bg-white rounded-xl overflow-hidden border border-amber-200">
            {d.validation.issues.slice(0, 15).map((i, k) => (
              <li key={k} className="px-4 py-2.5">
                <span className={`font-mono text-xs font-bold ${i.level === 'error' ? 'text-red-600' : 'text-amber-600'}`}>{i.code}</span> —{' '}
                <span className="text-slate-800 font-medium">{i.message}</span>{' '}
                {i.ref && <span className="text-slate-400 font-mono text-xs">({i.ref})</span>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {s && (
        <section className="mb-10">
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-lg font-bold" style={{ color: '#0F172A' }}>
              Class Distribution <span className="text-sm font-normal text-slate-500">({s.scope === 'train' ? 'Training Split' : 'All Images'})</span>
            </h2>
            {s.imbalance_ratio && (
              <div className="rounded-lg px-3 py-1 text-xs font-bold" style={{ backgroundColor: '#EEF2FF', color: '#4F46E5', border: '1px solid #C7D2FE' }}>
                Imbalance: <b className="font-extrabold">{s.imbalance_ratio}×</b> ({s.largest_class} vs {s.smallest_class})
              </div>
            )}
          </div>
          <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
            <div className="panel p-5 bg-white border border-slate-200 rounded-2xl shadow-sm">
              <DistributionChart rows={s.classes.map((c) => ({ label: c.label, original: c.count }))} />
            </div>
            <div className="panel overflow-hidden border border-slate-200 rounded-2xl bg-white shadow-sm h-fit">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr style={{ background: '#F8FAFC', borderBottom: '2px solid #E2E8F0' }}>
                    <th className="th" style={{ color: '#334155' }}>Class</th>
                    <th className="th" style={{ color: '#334155' }}>Count</th>
                    <th className="th" style={{ color: '#334155' }}>{s.annotation_type === 'multilabel' ? '% images' : '%'}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {s.classes.map((c) => (
                    <tr key={c.label} className="hover:bg-slate-50">
                      <td className="td font-bold" style={{ color: '#0D9488' }}>{c.label}</td>
                      <td className="td font-semibold text-slate-900">{c.count.toLocaleString()}</td>
                      <td className="td text-slate-500 font-medium">{c.percent_of_images}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {d.status !== 'failed' && (
        <section className="mb-10">
          <h2 className="mb-1 text-lg font-bold" style={{ color: '#0F172A' }}>Subject-Level Data Splits</h2>
          <p className="mb-4 max-w-prose text-sm font-medium" style={{ color: '#64748B' }}>
            Splits are created at the subject level before augmentation. Only training split is augmented — validation and test splits remain pristine.
          </p>
          {d.splits_defined ? (
            <div className="panel p-5 text-sm bg-white border border-teal-200/80 rounded-2xl shadow-sm mb-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: '#0D9488' }} />
                <span className="font-bold text-slate-800">
                  Splits Defined ({d.split_info.mode === 'create' ? `Stratified seed ${d.split_info.seed}` : 'From manifest'})
                </span>
              </div>
              <div className="grid grid-cols-3 gap-3">
                {Object.entries(s?.splits || {}).map(([k, v]) => (
                  <div key={k} className="rounded-xl p-3 border border-slate-200" style={{ backgroundColor: k === 'train' ? '#F0FDFA' : k === 'val' ? '#EEF2FF' : '#F8FAFC' }}>
                    <p className="text-xs font-bold uppercase tracking-wider text-slate-600">{k}</p>
                    <p className="text-lg font-extrabold mt-1" style={{ color: k === 'train' ? '#0D9488' : k === 'val' ? '#4F46E5' : '#0F172A' }}>
                      {v.images.toLocaleString()} <span className="text-xs font-normal text-slate-500">imgs</span>
                    </p>
                    <p className="text-xs font-medium text-slate-500">{v.patients.toLocaleString()} subjects</p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <Notice tone="warn" title="No evaluation splits created yet">
              Without patient-level splits, all images are treated as training data, which could lead to evaluation leakage.
            </Notice>
          )}

          <form
            className="mt-4 flex flex-wrap items-end gap-3 p-5 rounded-2xl bg-white border border-slate-200 shadow-sm"
            onSubmit={(e) => { e.preventDefault(); splitMut.mutate({ mode: 'create', ratios, seed: Number(seed) }) }}
          >
            {['train', 'val', 'test'].map((k) => (
              <Field key={k} label={`${k.toUpperCase()} ratio`}>
                <input
                  className="input w-28 font-bold"
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={ratios[k]}
                  onChange={(e) => setRatios({ ...ratios, [k]: e.target.value })}
                />
              </Field>
            ))}
            <Field label="Random Seed">
              <input
                className="input w-28 font-mono"
                type="number"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
              />
            </Field>
            <button
              className="btn-secondary"
              disabled={Math.abs(ratioSum - 1) > 1e-6 || splitMut.isPending}
            >
              {d.splits_defined ? 'Recreate Splits' : 'Create Patient-Level Splits'}
            </button>
            {d.has_supplied_splits && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => splitMut.mutate({ mode: 'use_existing' })}
              >
                Use Manifest Splits
              </button>
            )}
          </form>
          {Math.abs(ratioSum - 1) > 1e-6 && (
            <p className="mt-2 text-xs font-bold text-red-600">Ratios must sum to 1.0 (currently {ratioSum.toFixed(2)}).</p>
          )}
          <div className="mt-2"><ErrorNote error={splitMut.error} /></div>
        </section>
      )}

      <section>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-lg font-bold" style={{ color: '#0F172A' }}>
            Images {images.data && <span className="text-sm font-normal text-slate-500">({images.data.total.toLocaleString()} total)</span>}
          </h2>
          <div className="flex gap-2">
            <select aria-label="Filter by class" className="input w-44 font-semibold" value={label} onChange={(e) => { setLabel(e.target.value); setPage(0) }}>
              <option value="">All classes</option>
              {d.classes.map((c) => <option key={c}>{c}</option>)}
            </select>
            {d.splits_defined && (
              <select aria-label="Filter by split" className="input w-36 font-semibold" value={split} onChange={(e) => { setSplit(e.target.value); setPage(0) }}>
                <option value="">All splits</option>
                <option value="train">Train</option>
                <option value="val">Val</option>
                <option value="test">Test</option>
              </select>
            )}
          </div>
        </div>

        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
          {images.data?.items.map((im) => (
            <li key={im.image_id} className="panel overflow-hidden border border-slate-200 rounded-xl bg-white shadow-sm transition-transform hover:scale-[1.03] hover:shadow-md">
              <AuthImage className="aspect-square" alt={`${im.labels.join(', ')} image`} cacheKey={im.image_id} request={previewRequest(im.image_id, { max_size: 256 })} />
              <div className="p-2 text-xs">
                <p className="truncate font-bold text-slate-900">{im.labels.join(' + ')}</p>
                <p className="text-slate-500 font-medium mt-0.5">{im.split || 'no split'} · {im.dimensions.join('×')}</p>
              </div>
            </li>
          ))}
        </ul>

        {images.data && images.data.total > PAGE && (
          <div className="mt-6 flex items-center justify-center gap-3 text-sm">
            <button className="btn-secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>
              ← Previous
            </button>
            <span className="font-semibold text-slate-700">
              Page {page + 1} of {Math.ceil(images.data.total / PAGE)}
            </span>
            <button className="btn-secondary" disabled={(page + 1) * PAGE >= images.data.total} onClick={() => setPage(page + 1)}>
              Next →
            </button>
          </div>
        )}
      </section>
    </>
  )
}
