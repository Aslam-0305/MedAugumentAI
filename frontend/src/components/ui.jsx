export function PageHeader({ title, children, sub }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4 pb-5" style={{ borderBottom: '1px solid #E2E8F0' }}>
      <div>
        <div className="flex items-center gap-2 mb-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: 'linear-gradient(135deg, #0D9488, #6366F1)' }} />
          <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: '#0D9488' }}>MedAugment Studio</span>
        </div>
        <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight" style={{ color: '#0F172A' }}>{title}</h1>
        {sub && <p className="mt-2 max-w-2xl text-sm font-medium leading-relaxed" style={{ color: '#475569' }}>{sub}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2.5">{children}</div>
    </div>
  )
}

const PILLS = {
  ready: { bg: '#ECFDF5', color: '#065F46', border: '#A7F3D0', dot: '#10B981' },
  completed: { bg: '#ECFDF5', color: '#065F46', border: '#A7F3D0', dot: '#10B981' },
  passed: { bg: '#ECFDF5', color: '#065F46', border: '#A7F3D0', dot: '#10B981' },
  accepted: { bg: '#ECFDF5', color: '#065F46', border: '#A7F3D0', dot: '#10B981' },
  ready_with_issues: { bg: '#FFFBEB', color: '#92400E', border: '#FDE68A', dot: '#F59E0B' },
  warning: { bg: '#FFFBEB', color: '#92400E', border: '#FDE68A', dot: '#F59E0B' },
  cancelled: { bg: '#FFFBEB', color: '#92400E', border: '#FDE68A', dot: '#F59E0B' },
  failed: { bg: '#FEF2F2', color: '#991B1B', border: '#FECACA', dot: '#EF4444' },
  rejected: { bg: '#FEF2F2', color: '#991B1B', border: '#FECACA', dot: '#EF4444' },
  queued: { bg: '#F1F5F9', color: '#334155', border: '#CBD5E1', dot: '#94A3B8' },
  running: { bg: '#EEF2FF', color: '#3730A3', border: '#C7D2FE', dot: '#6366F1' },
  auto: { bg: '#F1F5F9', color: '#334155', border: '#CBD5E1', dot: '#94A3B8' },
}
const LABELS = { ready_with_issues: 'ready, with issues', auto: 'not reviewed' }
const DEFAULT_PILL = { bg: '#F1F5F9', color: '#334155', border: '#CBD5E1', dot: '#94A3B8' }

export function StatusPill({ status }) {
  const p = PILLS[status] || DEFAULT_PILL
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold tracking-wide shadow-sm"
      style={{ backgroundColor: p.bg, color: p.color, border: `1px solid ${p.border}` }}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${status === 'running' ? 'animate-pulse' : ''}`} style={{ backgroundColor: p.dot }} />
      {LABELS[status] || status}
    </span>
  )
}

export function Notice({ tone = 'info', title, children }) {
  const tones = {
    info: { bg: '#F0FDFA', border: '#99F6E4', title: '#0F766E', icon: '#0D9488' },
    warn: { bg: '#FFFBEB', border: '#FDE68A', title: '#B45309', icon: '#D97706' },
    bad: { bg: '#FEF2F2', border: '#FECACA', title: '#B91C1C', icon: '#DC2626' },
    ok: { bg: '#ECFDF5', border: '#A7F3D0', title: '#047857', icon: '#059669' },
  }
  const t = tones[tone] || tones.info
  return (
    <div
      role={tone === 'bad' ? 'alert' : 'status'}
      className="rounded-xl px-4 py-3.5 text-sm shadow-sm"
      style={{ backgroundColor: t.bg, border: `1px solid ${t.border}` }}
    >
      {title && <p className="font-bold text-sm" style={{ color: t.title }}>{title}</p>}
      <div className={title ? 'mt-1 text-slate-700' : 'text-slate-700'}>{children}</div>
    </div>
  )
}

export function ErrorNote({ error }) {
  if (!error) return null
  const msg = error?.response?.data?.error?.message || error?.message || String(error)
  return <Notice tone="bad" title="Action failed">{msg}</Notice>
}

export function ProgressBar({ percent = 0, label }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5 text-xs font-bold" style={{ color: '#475569' }}>
        <span>{label || 'Progress'}</span>
        <span style={{ color: '#0D9488' }}>{percent.toFixed(0)}%</span>
      </div>
      <div
        className="h-3 overflow-hidden rounded-full p-0.5"
        style={{ backgroundColor: '#E2E8F0', boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.06)' }}
        role="progressbar"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label || 'Progress'}
      >
        <div
          className="h-full rounded-full transition-all duration-500 ease-out shadow-sm"
          style={{
            width: `${Math.min(100, Math.max(0, percent))}%`,
            background: 'linear-gradient(90deg, #0D9488 0%, #6366F1 100%)',
          }}
        />
      </div>
    </div>
  )
}

export function Field({ label, hint, children }) {
  return (
    <label className="block text-sm">
      <span className="mb-1.5 block font-bold" style={{ color: '#1E293B' }}>{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs font-medium leading-relaxed" style={{ color: '#64748B' }}>{hint}</span>}
    </label>
  )
}

export function Empty({ title, children }) {
  return (
    <div className="panel p-10 text-center" style={{ background: 'linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%)' }}>
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl" style={{ backgroundColor: '#EEF2FF', color: '#6366F1' }}>
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
        </svg>
      </div>
      <p className="font-bold text-base" style={{ color: '#0F172A' }}>{title}</p>
      <div className="mt-2 flex justify-center text-sm font-medium" style={{ color: '#64748B' }}>{children}</div>
    </div>
  )
}

export function Loading({ what = 'Loading' }) {
  return (
    <div className="flex items-center gap-3 p-8">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-teal-600" />
      <span className="text-sm font-semibold" style={{ color: '#475569' }}>{what}…</span>
    </div>
  )
}

export const fmtDate = (s) => (s ? new Date(s).toLocaleString() : '—')
export const MODALITY = { xray: 'X-ray', ct: 'CT', mri: 'MRI' }
