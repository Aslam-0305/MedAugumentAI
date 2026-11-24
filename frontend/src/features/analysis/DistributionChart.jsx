import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

/** rows: [{label, original, additional?}] -> originals in vibrant teal, augmented additions in vivid indigo. */
export default function DistributionChart({ rows, height = 280 }) {
  const hasExtra = rows.some((r) => r.additional > 0)
  return (
    <div role="img" aria-label="Class distribution chart" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="#E2E8F0" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#475569', fontWeight: 600 }} interval={0} />
          <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: '#475569' }} />
          <Tooltip />
          {hasExtra && <Legend />}
          <Bar dataKey="original" name="Original" stackId="a" fill="#0D9488" radius={[0, 0, 0, 0]} />
          {hasExtra && <Bar dataKey="additional" name="Augmented (planned)" stackId="a" fill="#6366F1" radius={[4, 4, 0, 0]} />}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
