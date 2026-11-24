import { describe, expect, it } from 'vitest'
import { initialSelection, toAugmentationConfig } from './TransformPicker.jsx'

const catalog = {
  transforms: [
    { name: 'rotate', default_enabled: true, probability: 0.7, defaults: { max_degrees: 8 } },
    { name: 'elastic', default_enabled: false, probability: 0.3, defaults: { max_displacement: 3, smoothness: 8 } },
  ],
}

describe('transform selection', () => {
  it('enables only the modality defaults', () => {
    const sel = initialSelection(catalog)
    expect(sel.rotate.enabled).toBe(true)
    expect(sel.elastic.enabled).toBe(false)
  })

  it('sends only enabled transforms and does not share param objects with the catalog', () => {
    const sel = initialSelection(catalog)
    sel.rotate.params.max_degrees = 5
    const cfg = toAugmentationConfig(sel, { interpolation: 'linear', padding: 'background', output_dtype: 'preserve', allow_laterality_flip: false })
    expect(cfg.transforms).toEqual([{ name: 'rotate', probability: 0.7, params: { max_degrees: 5 } }])
    expect(catalog.transforms[0].defaults.max_degrees).toBe(8)
  })
})
