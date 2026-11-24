import { Field } from '../../components/ui.jsx'

/** value: {name: {enabled, probability, params}}.  Controls are generated from the backend catalog. */
export default function TransformPicker({ catalog, value, onChange }) {
  const set = (name, patch) => onChange({ ...value, [name]: { ...value[name], ...patch } })
  const setParam = (name, key, v) => set(name, { params: { ...value[name].params, [key]: v } })

  return (
    <div className="space-y-3.5">
      {catalog.transforms.map((t) => {
        const s = value[t.name]
        if (!s) return null
        return (
          <fieldset
            key={t.name}
            className={`rounded-2xl border p-5 transition-all duration-200 ${
              s.enabled
                ? 'bg-white shadow-md border-teal-300 ring-1 ring-teal-200/50'
                : 'bg-slate-50/70 border-slate-200 opacity-60'
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-1 h-5 w-5 rounded text-teal-600 focus:ring-teal-500 border-slate-300"
                  checked={s.enabled}
                  onChange={(e) => set(t.name, { enabled: e.target.checked })}
                />
                <div>
                  <span className="font-bold text-base text-slate-900 flex items-center gap-2">
                    {t.label}
                    {s.enabled && (
                      <span className="rounded-full px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wide bg-teal-100 text-teal-800">
                        Active
                      </span>
                    )}
                  </span>
                  <span className="block text-xs font-medium text-slate-600 mt-0.5">{t.description}</span>
                </div>
              </label>
              <span className="whitespace-nowrap text-xs font-bold uppercase tracking-wider rounded-md px-2 py-1 bg-slate-100 text-slate-600">
                {t.family}
              </span>
            </div>

            {t.caution && (
              <p className="mt-3 rounded-xl bg-amber-50 border border-amber-200 px-3.5 py-2 text-xs font-semibold text-amber-800">
                ⚠️ {t.caution}
              </p>
            )}

            {s.enabled && (
              <div className="mt-4 pt-4 border-t border-slate-100 grid gap-4 sm:grid-cols-3">
                <Field label="Probability" hint="Chance applied per image">
                  <input
                    className="input font-bold text-teal-700"
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    value={s.probability}
                    onChange={(e) => set(t.name, { probability: Number(e.target.value) })}
                  />
                </Field>
                {Object.entries(s.params).filter(([k]) => k !== 'axes').map(([key, val]) => {
                  const lim = t.limits[key]
                  const hint = [t.param_help[key], lim && `Limit: ${lim[0]}–${lim[1]}`].filter(Boolean).join(' · ')
                  return Array.isArray(val) ? (
                    <Field key={key} label={`${key.replace(/_/g, ' ')} [min, max]`} hint={hint}>
                      <div className="flex gap-2">
                        {val.map((n, i) => (
                          <input
                            key={i}
                            className="input font-semibold"
                            type="number"
                            step="0.01"
                            value={n}
                            onChange={(e) => setParam(t.name, key, val.map((x, j) => (j === i ? Number(e.target.value) : x)))}
                          />
                        ))}
                      </div>
                    </Field>
                  ) : (
                    <Field key={key} label={key.replace(/_/g, ' ')} hint={hint}>
                      <input
                        className="input font-semibold"
                        type="number"
                        step="any"
                        value={val}
                        onChange={(e) => setParam(t.name, key, Number(e.target.value))}
                      />
                    </Field>
                  )
                })}
              </div>
            )}
          </fieldset>
        )
      })}
      {catalog.blocked.length > 0 && (
        <details className="text-sm font-medium text-slate-500 mt-2 p-2">
          <summary className="cursor-pointer font-bold text-slate-700">Blocked for {catalog.label} ({catalog.blocked.length})</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
            {catalog.blocked.map((b) => (
              <li key={b.name}>
                <span className="font-bold text-slate-800">{b.label}</span>: {b.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

/** Build initial picker state from the catalog defaults. */
export function initialSelection(catalog) {
  return Object.fromEntries(catalog.transforms.map((t) => [t.name, { enabled: t.default_enabled, probability: t.probability, params: structuredClone(t.defaults) }]))
}

/** Convert picker state into the API's augmentation config. */
export function toAugmentationConfig(selection, opts) {
  return {
    transforms: Object.entries(selection).filter(([, s]) => s.enabled).map(([name, s]) => ({ name, probability: s.probability, params: s.params })),
    interpolation: opts.interpolation, padding: opts.padding, output_dtype: opts.output_dtype, allow_laterality_flip: opts.allow_laterality_flip,
  }
}
