import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client.js'
import { Empty, ErrorNote, Loading, MODALITY, PageHeader, StatusPill, fmtDate } from '../components/ui.jsx'

export default function Dashboard() {
  const datasets = useQuery({ queryKey: ['datasets'], queryFn: api.datasets })
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api.jobs(), refetchInterval: 4000 })
  const imageCount = (datasets.data || []).reduce((n, d) => n + d.counts.valid, 0)
  const active = (jobs.data || []).filter((j) => ['queued', 'running'].includes(j.status)).length

  return (
    <>
      <PageHeader title="Dashboard" sub="Balance an imbalanced radiology dataset with conservative, non-generative transformations, then export it with full provenance.">
        <Link to="/datasets/new" className="btn-primary">Upload dataset</Link>
      </PageHeader>
      <ErrorNote error={datasets.error || jobs.error} />

      <dl className="mb-10 grid gap-5 sm:grid-cols-3">
        {[
          ['Datasets', datasets.data?.length ?? '—', 'linear-gradient(135deg, #F0FDFA 0%, #CCFBF1 100%)', '#0D9488', '#99F6E4'],
          ['Valid images', datasets.data ? imageCount.toLocaleString() : '—', 'linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%)', '#6366F1', '#C7D2FE'],
          ['Jobs running or queued', jobs.data ? active : '—', 'linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)', '#D97706', '#FCD34D'],
        ].map(([k, v, bg, numColor, borderColor]) => (
          <div key={k} className="rounded-xl px-6 py-5 shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5"
            style={{ background: bg, border: `1px solid ${borderColor}` }}>
            <dt className="text-xs font-bold uppercase tracking-wider" style={{ color: '#64748B' }}>{k}</dt>
            <dd className="mt-2 text-3xl font-bold" style={{ color: numColor }}>{v}</dd>
          </div>
        ))}
      </dl>

      <section className="mb-10">
        <h2 className="mb-4">Datasets</h2>
        {datasets.isLoading ? <Loading /> : !datasets.data?.length ? (
          <Empty title="No datasets yet"><Link className="underline" style={{ color: '#0D9488' }} to="/datasets/new">Upload a ZIP with images and a CSV manifest to begin</Link></Empty>
        ) : (
          <div className="panel overflow-x-auto">
            <table className="w-full">
              <thead><tr style={{ borderBottom: '2px solid #E2E8F0' }}><th className="th">Name</th><th className="th">Modality</th><th className="th">Images</th><th className="th">Status</th><th className="th">Created</th></tr></thead>
              <tbody>
                {datasets.data.map((d) => (
                  <tr key={d.dataset_id} className="border-b border-line last:border-0 transition-colors" style={{ cursor: 'pointer' }}
                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F0FDFA'}
                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = ''}>
                    <td className="td"><Link className="font-semibold hover:underline" style={{ color: '#0D9488' }} to={`/datasets/${d.dataset_id}`}>{d.name}</Link></td>
                    <td className="td">{MODALITY[d.modality]}</td>
                    <td className="td">{d.counts.valid.toLocaleString()}{d.counts.invalid ? <span className="text-muted"> (+{d.counts.invalid} invalid)</span> : null}</td>
                    <td className="td"><StatusPill status={d.status} /></td>
                    <td className="td text-muted">{fmtDate(d.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-4">Recent jobs</h2>
        {!jobs.data?.length ? <p className="text-sm text-muted">No augmentation jobs yet.</p> : (
          <ul className="panel divide-y divide-line">
            {jobs.data.slice(0, 6).map((j) => (
              <li key={j.job_id} className="flex items-center justify-between gap-3 px-5 py-3.5 transition-colors"
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#EEF2FF'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = ''}>
                <Link className="font-semibold hover:underline" style={{ color: '#6366F1' }} to={`/jobs/${j.job_id}`}>{j.name}</Link>
                <span className="flex items-center gap-3 text-sm text-muted">{j.progress.done}/{j.progress.total}<StatusPill status={j.status} /></span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
