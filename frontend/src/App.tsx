import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, fetchHeatmap, planTrip } from './api'
import { ForecastSlider } from './components/ForecastSlider'
import { Legend } from './components/Legend'
import { RouteList } from './components/RouteList'
import { TripForm } from './components/TripForm'
import { hourOffset } from './format'
import type { HeatmapResponse, Place, PlanResponse, TripRequest } from './types'

// mapbox-gl is large; load it after the form so the page is usable immediately.
const MapView = lazy(() => import('./components/MapView').then((m) => ({ default: m.MapView })))

type Status = 'idle' | 'loading' | 'error'

export default function App() {
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState('')
  const [heatmapStatus, setHeatmapStatus] = useState<Status>('idle')
  const [selectedId, setSelectedId] = useState('')
  const [hour, setHour] = useState(0)
  const [endpoints, setEndpoints] = useState<{ origin: Place; destination: Place } | null>(null)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  const submit = useCallback((trip: TripRequest, places: { origin: Place; destination: Place }) => {
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort

    setStatus('loading')
    setHeatmapStatus('loading')
    setError('')
    setHeatmap(null)

    // Routes and heatmap load independently, so the routes appear as soon as they are ready.
    planTrip(trip, abort.signal)
      .then((result) => {
        setPlan(result)
        setSelectedId(result.recommended_route_id)
        setEndpoints(places)
        setStatus('idle')
        return result
      })
      .catch((err: unknown) => {
        if (abort.signal.aborted) return
        setStatus('error')
        setError(err instanceof ApiError ? err.message : 'Something went wrong planning this trip.')
      })

    fetchHeatmap(trip, abort.signal)
      .then((result) => {
        setHeatmap(result)
        setHour(hourOffset(result.start, trip.departure_time, result.hours - 1))
        setHeatmapStatus('idle')
      })
      .catch((err: unknown) => {
        if (!abort.signal.aborted) {
          setHeatmapStatus('error')
          console.error('Heatmap failed', err)
        }
      })
  }, [])

  const departureHour = heatmap && plan ? hourOffset(heatmap.start, plan.departure_time, heatmap.hours - 1) : 0

  return (
    <div className="app">
      <aside className="sidebar">
        <header>
          <h1>Weather-Aware Truck Routing</h1>
          <p className="muted">Compare three routes by weather risk, load weight and drive time.</p>
        </header>

        <TripForm busy={status === 'loading'} onSubmit={submit} />

        {status === 'error' && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}
        {status === 'loading' && (
          <p className="loading" role="status">
            Finding routes and checking weather at each checkpoint…
          </p>
        )}
        {plan && status !== 'loading' && <RouteList plan={plan} selectedId={selectedId} onSelect={setSelectedId} />}
      </aside>

      <main className="map-panel">
        <Suspense fallback={<div className="map-missing">Loading map…</div>}>
          <MapView
            plan={plan}
            selectedId={selectedId}
            heatmap={heatmap}
            hour={hour}
            endpoints={endpoints}
            onSelectRoute={setSelectedId}
          />
        </Suspense>
        <div className="map-overlay">
          <Legend />
          {heatmap && (
            <ForecastSlider
              start={heatmap.start}
              hours={heatmap.hours}
              value={hour}
              departureHour={departureHour}
              onChange={setHour}
            />
          )}
          {heatmapStatus === 'loading' && <p className="muted small">Loading forecast heatmap…</p>}
          {heatmapStatus === 'error' && <p className="muted small">Forecast heatmap unavailable.</p>}
        </div>
      </main>
    </div>
  )
}
