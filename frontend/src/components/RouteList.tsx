import { formatDuration, formatMiles, formatTime } from '../format'
import { RISK_COLORS, RISK_LABELS, RISK_LEVELS } from '../risk'
import type { PlanResponse, Route } from '../types'

interface Props {
  plan: PlanResponse
  selectedId: string
  onSelect: (id: string) => void
}

function RiskBar({ route }: { route: Route }) {
  const total = RISK_LEVELS.reduce<number>((sum, level) => sum + route.metrics.miles_by_level[level], 0) || 1
  return (
    <>
      <div className="risk-bar" role="img" aria-label="Miles by risk level">
        {RISK_LEVELS.map((level) => {
          const miles = route.metrics.miles_by_level[level]
          return miles > 0 ? (
            <span key={level} style={{ width: `${(miles / total) * 100}%`, background: RISK_COLORS[level] }} />
          ) : null
        })}
      </div>
      <ul className="risk-miles">
        {RISK_LEVELS.filter((level) => route.metrics.miles_by_level[level] > 0).map((level) => (
          <li key={level}>
            <i style={{ background: RISK_COLORS[level] }} />
            {RISK_LABELS[level]} {formatMiles(route.metrics.miles_by_level[level])}
          </li>
        ))}
      </ul>
    </>
  )
}

export function RouteList({ plan, selectedId, onSelect }: Props) {
  const ordered = [...plan.routes].sort((a, b) => a.rank - b.rank)
  return (
    <section aria-label="Route options">
      <p className={`recommendation${plan.recommendation.all_blocked ? ' warning' : ''}`}>
        <strong>Recommended: Route {plan.recommended_route_id}.</strong> {plan.recommendation.explanation}
      </p>
      <ul className="routes">
        {ordered.map((route) => (
          <li key={route.id}>
            <button
              type="button"
              className={`route-card${route.id === selectedId ? ' selected' : ''}`}
              aria-pressed={route.id === selectedId}
              onClick={() => onSelect(route.id)}
            >
              <div className="route-head">
                <span className="route-name">{route.name}</span>
                {route.recommended && <span className="badge good">Recommended</span>}
                {route.blocked && <span className="badge bad">No Travel</span>}
                <span className="rank">#{route.rank}</span>
              </div>
              {route.summary && <p className="via">via {route.summary}</p>}
              <dl className="stats">
                <div>
                  <dt>Distance</dt>
                  <dd>{formatMiles(route.distance_miles)}</dd>
                </div>
                <div>
                  <dt>Drive time</dt>
                  <dd>{formatDuration(route.duration_s)}</dd>
                </div>
                <div>
                  <dt>Arrive</dt>
                  <dd>{formatTime(route.arrival_time)}</dd>
                </div>
                <div>
                  <dt>Avg risk</dt>
                  <dd>{route.metrics.avg_risk.toFixed(2)}</dd>
                </div>
              </dl>
              <RiskBar route={route} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
