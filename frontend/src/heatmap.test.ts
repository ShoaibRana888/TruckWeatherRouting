import { describe, expect, it } from 'vitest'
import { heatWeightExpression } from './heatmap'

describe('heatWeightExpression', () => {
  it('reads the property for the requested forecast hour', () => {
    expect(JSON.stringify(heatWeightExpression(17))).toContain('"r17"')
  })
  it('maps each risk level to a weight that increases with risk', () => {
    const expr = heatWeightExpression(0) as unknown[]
    const stops = expr.slice(3) as number[]
    const weights = stops.filter((_, i) => i % 2 === 1)
    expect(weights).toEqual([...weights].sort((a, b) => a - b))
    expect(weights).toHaveLength(5)
  })
})
