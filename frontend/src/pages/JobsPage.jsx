import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client.js'
import { Empty, ErrorNote, Loading, PageHeader, StatusPill, fmtDate } from '../components/ui.jsx'

export default function JobsPage() {
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api.jobs(), refetchInterval: 3000 })
  return (
    <>
      <PageHeader title="Augmentation Jobs" sub="Track progress of conservative transform pipelines and view validated output datasets." />
      <ErrorNote error={jobs.error} />
      {jobs.isLoading ? <Loading what="Loading jobs" /> : !jobs.data?.length ? (
        <Empty title="No jobs yet">
          <span>Plan an augmentation from a dataset page to start generating samples.</span>
        </Empty>
      ) : (
        <div className="panel overflow-hidden border border-slate-200/90 shadow-sm rounded-2xl bg-white">
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr style={{ background: 'linear-gradient(to right, #F8FAFC, #F1F5F9)', borderBottom: '2px solid #E2E8F0' }}>
                  <th className="th" style={{ color: '#334155', fontWeight: 700 }}>Job Name</th>
                  <th className="th" style={{ color: '#334155', fontWeight: 700 }}>Progress</th>
                  <th className="th" style={{ color: '#334155', fontWeight: 700 }}>Status</th>
                  <th className="th" style={{ color: '#334155', fontWeight: 700 }}>Created</th>
                  <th className="th" style={{ color: '#334155', fontWeight: 700 }}>Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {jobs.data.map((j) => (
                  <tr
                    key={j.job_id}
                    className="transition-colors duration-150"
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#F0FDFA')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '')}
                  >
                    <td className="td font-bold">
                      <Link
                        className="transition-colors hover:underline flex items-center gap-2"
                        style={{ color: '#4F46E5' }}
                        to={`/jobs/${j.job_id}`}
                      >
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: '#6366F1' }} />
                        {j.name}
                      </Link>
                    </td>
                    <td className="td font-semibold" style={{ color: '#1E293B' }}>
                      <span className="font-bold" style={{ color: '#0D9488' }}>{j.progress.done.toLocaleString()}</span>
                      <span className="mx-1 text-slate-400">/</span>
                      <span className="text-slate-600">{j.progress.total.toLocaleString()}</span>
                    </td>
                    <td className="td">
                      <StatusPill status={j.status} />
                    </td>
                    <td className="td text-xs font-medium" style={{ color: '#64748B' }}>
                      {fmtDate(j.created_at)}
                    </td>
                    <td className="td">
                      {j.status === 'completed' ? (
                        <Link
                          className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-bold text-white shadow-sm transition-transform hover:scale-105"
                          style={{ background: 'linear-gradient(135deg, #0D9488, #059669)' }}
                          to={`/jobs/${j.job_id}/results`}
                        >
                          Review Results →
                        </Link>
                      ) : (
                        <Link
                          className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-bold transition-colors"
                          style={{ color: '#4F46E5', backgroundColor: '#EEF2FF' }}
                          to={`/jobs/${j.job_id}`}
                        >
                          View Details
                        </Link>
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
