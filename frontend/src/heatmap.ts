import type { ExpressionSpecification } from 'mapbox-gl'

/** Heatmap weight for forecast hour `hour`: each point's risk level (0-4) mapped to intensity. */
// prettier-ignore
export const heatWeightExpression = (hour: number): ExpressionSpecification => [
  'interpolate',
  ['linear'],
  ['coalesce', ['get', `r${hour}`], 0],
  0, 0.1,
  1, 0.3,
  2, 0.5,
  3, 0.75,
  4, 1,
]

// prettier-ignore
export const HEAT_COLOR: ExpressionSpecification = [
  'interpolate',
  ['linear'],
  ['heatmap-density'],
  0, 'rgba(46,158,91,0)',
  0.1, 'rgba(46,158,91,0.35)',
  0.3, 'rgba(46,158,91,0.55)',
  0.45, 'rgba(227,180,27,0.7)',
  0.6, 'rgba(240,138,36,0.78)',
  0.8, 'rgba(217,54,62,0.85)',
  1, 'rgba(91,26,122,0.9)',
]
