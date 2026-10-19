import type { RiskLevel } from './types'

export const RISK_LEVELS: readonly RiskLevel[] = [0, 1, 2, 3, 4]

export const RISK_LABELS: Record<RiskLevel, string> = {
  0: 'Low',
  1: 'Moderate',
  2: 'High',
  3: 'Severe',
  4: 'No Travel',
}

export const RISK_COLORS: Record<RiskLevel, string> = {
  0: '#2e9e5b',
  1: '#e3b41b',
  2: '#f08a24',
  3: '#d9363e',
  4: '#5b1a7a',
}

/** Mapbox `match` expression turning a numeric `level` property into its colour. */
export const levelColorExpression = (property = 'level'): unknown[] => [
  'match',
  ['get', property],
  ...RISK_LEVELS.flatMap((level) => [level, RISK_COLORS[level]]),
  RISK_COLORS[0],
]
