import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client.js'
import { ErrorNote, Field, Notice, PageHeader, ProgressBar } from '../components/ui.jsx'

const FORMATS = {
  xray: 'PNG, JPEG, TIFF or DICOM (.dcm). One 2D image per row.',
  ct: 'NIfTI (.nii/.nii.gz) volumes or a DICOM series folder. Values should be in Hounsfield Units.',
  mri: 'NIfTI volumes (3D or 4D multi-sequence), a DICOM series folder, or several aligned files per row separated by “;”.',
}

export default function UploadPage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [modality, setModality] = useState('xray')
  const [layout, setLayout] = useState('manifest')
  const [archive, setArchive] = useState(null)
  const [manifest, setManifest] = useState(null)
  const [pct, setPct] = useState(0)

  const create = useMutation({
    mutationFn: () => {
      const form = new FormData()
      form.append('name', name)
      form.append('modality', modality)
      form.append('layout', layout)
      form.append('files', archive)
      if (layout === 'manifest' && manifest) form.append('manifest', manifest)
      setPct(0)
      return api.createDataset(form, (e) => e.total && setPct((100 * e.loaded) / e.total))
    },
    onSuccess: (d) => { qc.invalidateQueries({ queryKey: ['datasets'] }); if (d.status !== 'failed') nav(`/datasets/${d.dataset_id}`) },
  })
  const result = create.data
  const canSubmit = name.trim() && archive && !create.isPending

  return (
    <>
      <PageHeader
        title="Upload Dataset"
        sub="Files are validated by content, not just extension. Patient IDs are pseudonymised on arrival and originals are never modified."
      />
      <form
        className="panel max-w-2xl space-y-6 p-8 bg-white border border-slate-200/90 shadow-sm rounded-2xl"
        onSubmit={(e) => { e.preventDefault(); create.mutate() }}
      >
        <Field label="Dataset Name">
          <input className="input font-semibold" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Chest X-ray pilot" required />
        </Field>
        
        <Field label="Modality" hint={FORMATS[modality]}>
          <select className="input font-semibold" style={{ color: '#0F172A' }} value={modality} onChange={(e) => setModality(e.target.value)}>
            <option value="xray">X-ray (2D)</option>
            <option value="ct">CT (3D Volume)</option>
            <option value="mri">MRI (Multi-sequence)</option>
          </select>
        </Field>

        <fieldset className="rounded-xl p-4 bg-slate-50 border border-slate-200">
          <legend className="px-2 text-xs font-bold uppercase tracking-wider text-slate-700">Annotation Layout</legend>
          <div className="space-y-3 text-sm mt-1">
            <label className="flex items-start gap-3 cursor-pointer">
              <input type="radio" className="mt-1 h-4 w-4 text-teal-600 focus:ring-teal-500" checked={layout === 'manifest'} onChange={() => setLayout('manifest')} />
              <div>
                <span className="font-bold text-slate-900">CSV manifest</span>
                <p className="text-xs text-slate-600 mt-0.5">image_path, optional patient_id / split / mask_path, and label columns.</p>
              </div>
            </label>
            <label className="flex items-start gap-3 cursor-pointer">
              <input type="radio" className="mt-1 h-4 w-4 text-teal-600 focus:ring-teal-500" checked={layout === 'folders'} onChange={() => setLayout('folders')} />
              <div>
                <span className="font-bold text-slate-900">Folder per class</span>
                <p className="text-xs text-slate-600 mt-0.5">Single-label only: <code>Class/image files</code>.</p>
              </div>
            </label>
          </div>
        </fieldset>

        <Field label="Dataset archive (.zip)" hint="Images, plus the manifest if you don’t upload it separately.">
          <div className="mt-1.5 flex items-center rounded-xl border border-slate-200 bg-slate-50 p-2.5 shadow-sm transition-all hover:border-teal-400 focus-within:border-teal-500 focus-within:ring-2 focus-within:ring-teal-100">
            <input
              type="file"
              accept=".zip"
              className="block w-full text-sm font-semibold text-slate-700 cursor-pointer"
              onChange={(e) => setArchive(e.target.files[0] || null)}
              required
            />
          </div>
        </Field>

        {layout === 'manifest' && (
          <Field label="Manifest (.csv), optional if inside the ZIP">
            <div className="mt-1.5 flex items-center rounded-xl border border-slate-200 bg-slate-50 p-2.5 shadow-sm transition-all hover:border-teal-400 focus-within:border-teal-500 focus-within:ring-2 focus-within:ring-teal-100">
              <input
                type="file"
                accept=".csv,text/csv"
                className="block w-full text-sm font-semibold text-slate-700 cursor-pointer"
                onChange={(e) => setManifest(e.target.files[0] || null)}
              />
            </div>
          </Field>
        )}

        {create.isPending && <ProgressBar percent={pct} label="Upload Progress" />}
        {create.isPending && pct >= 100 && (
          <p className="text-sm font-bold text-teal-700">
            Upload complete. Validating every image — large volumes can take a while.
          </p>
        )}
        <ErrorNote error={create.error} />

        <div className="pt-2">
          <button className="btn-primary w-full sm:w-auto" disabled={!canSubmit}>
            {create.isPending ? 'Uploading & Validating…' : 'Upload and Validate Dataset'}
          </button>
        </div>
      </form>

      {result?.status === 'failed' && (
        <div className="mt-8 max-w-2xl space-y-4">
          <Notice tone="bad" title="No valid images were found">
            Fix the problems below and upload again.
          </Notice>
          <ul className="panel divide-y divide-slate-100 text-sm bg-white border border-red-200 rounded-2xl shadow-sm overflow-hidden">
            {result.validation.issues.slice(0, 12).map((i, k) => (
              <li key={k} className="px-5 py-3 hover:bg-red-50/50 transition-colors">
                <span className="font-bold text-red-600 font-mono text-xs">{i.code}</span> —{' '}
                <span className="text-slate-800 font-medium">{i.message}</span>{' '}
                {i.ref && <span className="text-slate-500 font-mono text-xs">({i.ref})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  )
}
