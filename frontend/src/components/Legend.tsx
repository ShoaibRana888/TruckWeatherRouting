import { RISK_COLORS, RISK_LABELS, RISK_LEVELS } from '../risk'

export function Legend() {
  return (
    <ul className="legend" aria-label="Risk levels">
      {RISK_LEVELS.map((level) => (
        <li key={level}>
          <i style={{ background: RISK_COLORS[level] }} />
          {RISK_LABELS[level]}
        </li>
      ))}
    </ul>
  )
}
