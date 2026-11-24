import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client.js'
import AuthImage, { augmentedPreviewRequest, previewRequest } from '../components/AuthImage.jsx'
import { ErrorNote, Field, Loading, MODALITY, Notice, PageHeader } from '../components/ui.jsx'
import DistributionChart from '../features/analysis/DistributionChart.jsx'
import TransformPicker, { initialSelection, toAugmentationConfig } from '../features/augmentation/TransformPicker.jsx'

const STRATEGIES = {
  balance_largest: 'Balance to the largest class',
  target_count: 'Same target count for every class',
  custom: 'Custom target per class',
}

export default function AugmentPage() {
  const { datasetId } = useParams()
  const nav = useNavigate()
  const ds = useQuery({ queryKey: ['dataset', datasetId], queryFn: () => api.dataset(datasetId) })
  const modality = ds.data?.modality
  const catalog = useQuery({ queryKey: ['catalog', modality], queryFn: () => api.transforms(modality), enabled: !!modality })
  const images = useQuery({ queryKey: ['preview-images', datasetId], queryFn: () => api.images(datasetId, { status: 'valid', split: ds.data?.splits_defined ? 'train' : undefined, limit: 40 }), enabled: !!ds.data })

  const [bal, setBal] = useState({ strategy: 'balance_largest', target_count: 100, max_expansion_factor: 10, per_class_cap: '', excluded: [], custom: {} })
  const [selection, setSelection] = useState(null)
  const [opts, setOpts] = useState({ interpolation: 'linear', padding: 'background', output_dtype: 'preserve', allow_laterality_flip: false })
  const [seed, setSeed] = useState(42)
  const [name, setName] = useState('')
  const [planKey, setPlanKey] = useState(null)
  const [previewId, setPreviewId] = useState('')
  const [previewSeed, setPreviewSeed] = useState(0)
  const [slice, setSlice] = useState('')

  useEffect(() => { if (catalog.data && !selection) setSelection(initialSelection(catalog.data)) }, [catalog.data, selection])
  useEffect(() => { if (!previewId && images.data?.items.length) setPreviewId(images.data.items[0].image_id) }, [images.data, previewId])

  const payload = useMemo(() => {
    if (!selection) return null
    const custom = Object.fromEntries(Object.entries(bal.custom).filter(([, v]) => v !== '' && Number(v) > 0).map(([k, v]) => [k, Number(v)]))
    return {
      dataset_id: datasetId, seed: Number(seed), name: name || undefined,
      balancing: {
        strategy: bal.strategy, max_expansion_factor: Number(bal.max_expansion_factor), excluded_classes: bal.excluded,
        ...(bal.strategy === 'target_count' ? { target_count: Number(bal.target_count) } : {}),
        ...(bal.strategy === 'custom' ? { custom_targets: custom } : {}),
        ...(bal.per_class_cap !== '' ? { per_class_cap: Number(bal.per_class_cap) } : {}),
      },
      augmentation: toAugmentationConfig(selection, opts),
    }
  }, [bal, selection, opts, seed, name, datasetId])
  const key = JSON.stringify(payload)

  const plan = useMutation({ mutationFn: () => api.plan(payload), onSuccess: () => setPlanKey(key) })
  const start = useMutation({ mutationFn: () => api.createJob(payload), onSuccess: (j) => nav(`/jobs/${j.job_id}`) })
  const stale = plan.data && planKey !== key

  if (ds.isLoading || catalog.isLoading || !selection) return <Loading what="Loading augmentation engine" />
  if (ds.error || catalog.error) return <ErrorNote error={ds.error || catalog.error} />
  const d = ds.data
  const toggleExcluded = (c) => setBal({ ...bal, excluded: bal.excluded.includes(c) ? bal.excluded.filter((x) => x !== c) : [...bal.excluded, c] })
  const volume = d.modality !== 'xray'
  const previewBody = { dataset_id: datasetId, image_id: previewId, augmentation: payload.augmentation, seed: previewSeed, slice_index: slice === '' ? undefined : Number(slice) }

  return (
    <>
      <PageHeader
        title="Plan Dataset Augmentation"
        sub={`${d.name} · ${MODALITY[d.modality]}. Configure conservative transformations, inspect visual samples, and verify projected balancing.`}
      >
        <Link to={`/datasets/${datasetId}`} className="btn-secondary">
          ← Back to Dataset
        </Link>
      </PageHeader>

      {!d.splits_defined && (
        <div className="mb-6">
          <Notice tone="warn" title="No evaluation splits defined">
            All images will be treated as training data. <Link className="font-bold underline text-amber-900" to={`/datasets/${datasetId}`}>Create patient-level splits first</Link> to prevent data leakage.
          </Notice>
        </div>
      )}

      {/* Balancing Targets */}
      <section className="mb-8">
        <h2 className="mb-3 text-lg font-bold" style={{ color: '#0F172A' }}>1. Balancing Strategy</h2>
        <div className="panel grid gap-5 p-6 md:grid-cols-2 bg-white border border-slate-200 rounded-2xl shadow-sm">
          <Field label="Strategy">
            <select className="input font-semibold" style={{ color: '#0F172A' }} value={bal.strategy} onChange={(e) => setBal({ ...bal, strategy: e.target.value })}>
              {Object.entries(STRATEGIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          {bal.strategy === 'target_count' && (
            <Field label="Target Count Per Class" hint="Classes with more than this number are preserved untouched.">
              <input className="input font-bold" type="number" min="1" value={bal.target_count} onChange={(e) => setBal({ ...bal, target_count: e.target.value })} />
            </Field>
          )}
          <Field label="Maximum Expansion Factor" hint="A class may grow to at most this multiple of original size.">
            <input className="input font-bold" type="number" min="1" step="0.5" value={bal.max_expansion_factor} onChange={(e) => setBal({ ...bal, max_expansion_factor: e.target.value })} />
          </Field>
          <Field label="Per-Class Cap on Added Samples (Optional)">
            <input className="input font-bold" type="number" min="0" value={bal.per_class_cap} onChange={(e) => setBal({ ...bal, per_class_cap: e.target.value })} />
          </Field>
          <fieldset className="md:col-span-2 pt-3 border-t border-slate-100">
            <legend className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-700">
              {bal.strategy === 'custom' ? 'Custom Target per Class and Exclusions' : 'Classes to Leave Unaugmented'}
            </legend>
            <div className="flex flex-wrap gap-x-6 gap-y-2.5">
              {d.classes.map((c) => (
                <div key={c} className="flex items-center gap-2 text-sm p-2 rounded-lg bg-slate-50 border border-slate-200">
                  <label className="flex items-center gap-2 cursor-pointer font-semibold text-slate-800">
                    <input type="checkbox" className="h-4 w-4 rounded text-teal-600 focus:ring-teal-500" checked={bal.excluded.includes(c)} onChange={() => toggleExcluded(c)} />
                    {bal.strategy === 'custom' ? 'Skip' : c}
                  </label>
                  {bal.strategy === 'custom' && (
                    <>
                      <span className="font-bold text-slate-900">{c}</span>
                      <input aria-label={`Target for ${c}`} className="input w-24 font-bold" type="number" min="1" value={bal.custom[c] ?? ''} onChange={(e) => setBal({ ...bal, custom: { ...bal.custom, [c]: e.target.value } })} />
                    </>
                  )}
                </div>
              ))}
            </div>
          </fieldset>
        </div>
      </section>

      {/* Transforms Selection */}
      <section className="mb-8">
        <h2 className="mb-1 text-lg font-bold" style={{ color: '#0F172A' }}>2. Conservative Transformations</h2>
        <ul className="mb-4 list-disc space-y-1 pl-5 text-xs font-medium text-slate-500">
          {catalog.data.policy_notes.map((n) => <li key={n}>{n}</li>)}
        </ul>
        <TransformPicker catalog={catalog.data} value={selection} onChange={setSelection} />
        {selection.flip?.enabled && (
          <div className="mt-4">
            <Notice tone="warn" title="Laterality Mirror Check">
              <label className="flex items-center gap-2 font-bold cursor-pointer text-amber-900 mt-1">
                <input type="checkbox" className="h-4 w-4 rounded text-amber-600" checked={opts.allow_laterality_flip} onChange={(e) => setOpts({ ...opts, allow_laterality_flip: e.target.checked })} />
                I confirm this clinical pathology is invariant to left-right laterality mirroring.
              </label>
            </Notice>
          </div>
        )}
        <div className="panel mt-4 grid gap-5 p-6 sm:grid-cols-3 bg-white border border-slate-200 rounded-2xl shadow-sm">
          <Field label="Interpolation">
            <select className="input font-semibold" value={opts.interpolation} onChange={(e) => setOpts({ ...opts, interpolation: e.target.value })}>
              <option value="linear">Linear (Recommended)</option>
              <option value="nearest">Nearest</option>
              <option value="cubic">Cubic</option>
            </select>
          </Field>
          <Field label="Padding Mode" hint="Fills pixels moved outside the field">
            <select className="input font-semibold" value={opts.padding} onChange={(e) => setOpts({ ...opts, padding: e.target.value })}>
              <option value="background">Background Tissue Value</option>
              <option value="edge">Repeat Edge</option>
              <option value="reflect">Reflect</option>
            </select>
          </Field>
          <Field label="Output Data Type">
            <select className="input font-semibold" value={opts.output_dtype} onChange={(e) => setOpts({ ...opts, output_dtype: e.target.value })}>
              <option value="preserve">Preserve Source Type</option>
              <option value="float32">float32</option>
            </select>
          </Field>
        </div>
      </section>

      {/* Visual Example Preview */}
      <section className="mb-8">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-lg font-bold" style={{ color: '#0F172A' }}>3. Real-Time Sample Preview</h2>
          <div className="flex flex-wrap items-end gap-2.5">
            <Field label="Sample Image">
              <select className="input w-56 font-semibold" value={previewId} onChange={(e) => setPreviewId(e.target.value)}>
                {images.data?.items.map((im) => (
                  <option key={im.image_id} value={im.image_id}>{im.labels.join('+')} · {im.image_id.slice(-6)}</option>
                ))}
              </select>
            </Field>
            {volume && (
              <Field label="Slice">
                <input className="input w-20 font-bold" type="number" min="0" value={slice} placeholder="mid" onChange={(e) => setSlice(e.target.value)} />
              </Field>
            )}
            <button className="btn-secondary" onClick={() => setPreviewSeed(previewSeed + 1)}>
              🎲 New Seed
            </button>
          </div>
        </div>
        {previewId && (
          <div className="grid gap-6 sm:grid-cols-2">
            {[
              ['Original Source Image', previewRequest(previewId, { slice_index: slice === '' ? undefined : Number(slice) }), `o-${previewId}-${slice}`, '#0D9488', '#CCFBF1', '#065F46'],
              ['Transformed Augmented Sample', augmentedPreviewRequest(previewBody), `a-${previewId}-${previewSeed}-${slice}-${key}`, '#6366F1', '#EEF2FF', '#3730A3'],
            ].map(([lbl, req, ck, border, badgeBg, badgeTxt]) => (
              <figure key={lbl} className="overflow-hidden rounded-2xl border bg-slate-950 shadow-md" style={{ borderColor: border }}>
                <AuthImage className="aspect-square" alt={lbl} cacheKey={ck} request={req} />
                <figcaption className="flex items-center justify-between px-4 py-3 bg-slate-900 border-t border-slate-800">
                  <span className="text-xs font-bold text-white tracking-wide">{lbl}</span>
                  <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full" style={{ backgroundColor: badgeBg, color: badgeTxt }}>
                    {lbl.includes('Original') ? 'Preserved' : 'Simulated'}
                  </span>
                </figcaption>
              </figure>
            ))}
          </div>
        )}
        <p className="mt-2 text-xs font-medium text-slate-500">
          Previews are interactive and test parameters immediately against validation bounds without saving to storage.
        </p>
      </section>

      {/* Projected Result Plan */}
      <section className="mb-8">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-bold" style={{ color: '#0F172A' }}>4. Projected Distribution Plan</h2>
          <button className="btn-secondary" onClick={() => plan.mutate()} disabled={plan.isPending}>
            {plan.isPending ? 'Calculating Plan…' : plan.data ? 'Recalculate Plan' : 'Calculate Balancing Plan'}
          </button>
        </div>
        <ErrorNote error={plan.error} />
        {stale && <Notice tone="warn">Settings modified. Click Recalculate Plan before executing.</Notice>}
        {plan.data && (
          <div className="mt-4 space-y-4">
            <div className="grid gap-6 lg:grid-cols-[1fr_24rem]">
              <div className="panel p-5 bg-white border border-slate-200 rounded-2xl shadow-sm">
                <DistributionChart rows={plan.data.classes.map((c) => ({ label: c.label, original: c.original, additional: Math.max(0, c.projected - c.original) }))} />
              </div>
              <div className="panel overflow-hidden border border-slate-200 rounded-2xl bg-white shadow-sm h-fit">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr style={{ background: '#F8FAFC', borderBottom: '2px solid #E2E8F0' }}>
                      <th className="th" style={{ color: '#334155' }}>Class</th>
                      <th className="th" style={{ color: '#334155' }}>Current</th>
                      <th className="th" style={{ color: '#334155' }}>Target</th>
                      <th className="th" style={{ color: '#334155' }}>Projected</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {plan.data.classes.map((c) => (
                      <tr key={c.label} className="hover:bg-slate-50">
                        <td className="td font-bold" style={{ color: '#0D9488' }}>{c.label}</td>
                        <td className="td font-semibold text-slate-800">{c.original}</td>
                        <td className="td text-slate-500 font-medium">{c.excluded ? 'Skipped' : c.target}</td>
                        <td className="td font-extrabold" style={{ color: '#4F46E5' }}>
                          {c.projected}
                          {c.capped_by && <span className="block text-[11px] font-bold text-amber-600">Capped by {c.capped_by.replace(/_/g, ' ')}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="rounded-xl p-4 bg-teal-50 border border-teal-200 flex items-center justify-between text-sm">
              <span className="font-semibold text-teal-900">
                <b>{plan.data.total_additional.toLocaleString()}</b> synthesized samples from {plan.data.total_original.toLocaleString()} training originals · Est. {plan.data.estimated_storage_mb} MB storage
              </span>
            </div>
            {plan.data.warnings.length > 0 && (
              <Notice tone="warn" title="Safety Review">
                <ul className="list-disc space-y-1 pl-5 text-slate-700 font-medium">
                  {plan.data.warnings.map((w) => <li key={w}>{w}</li>)}
                </ul>
              </Notice>
            )}
          </div>
        )}
      </section>

      {/* Execution Launcher Bar */}
      <div className="panel flex flex-wrap items-end gap-5 p-6 bg-white border border-slate-200/90 shadow-md rounded-2xl">
        <Field label="Job Name (Optional)">
          <input className="input w-72 font-semibold" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Chest-balanced-v1" />
        </Field>
        <Field label="Random Seed" hint="Identical seed = reproducible run">
          <input className="input w-36 font-mono font-bold" type="number" min="0" value={seed} onChange={(e) => setSeed(e.target.value)} />
        </Field>
        <button
          className="btn-primary"
          disabled={!plan.data || stale || start.isPending || plan.data.total_additional === 0}
          onClick={() => start.mutate()}
        >
          {start.isPending ? 'Initiating Pipeline…' : `Start Generation (${plan.data ? plan.data.total_additional.toLocaleString() : 0} Samples)`}
        </button>
        {!plan.data && <p className="text-xs font-bold text-slate-500 pb-2">Calculate the plan above to enable execution.</p>}
      </div>
      <div className="mt-3"><ErrorNote error={start.error} /></div>
    </>
  )
}
