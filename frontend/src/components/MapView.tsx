import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { useEffect, useRef, useState } from 'react'
import { formatDuration, formatMiles, formatTime } from '../format'
import { HEAT_COLOR, heatWeightExpression } from '../heatmap'
import { levelColorExpression, RISK_COLORS } from '../risk'
import type { Checkpoint, HeatmapResponse, Place, PlanResponse, Route } from '../types'

const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN as string | undefined
const STYLE = (import.meta.env.VITE_MAP_STYLE as string | undefined) || 'mapbox://styles/mapbox/light-v11'

type Expr = mapboxgl.ExpressionSpecification

interface Props {
  plan: PlanResponse | null
  selectedId: string
  heatmap: HeatmapResponse | null
  hour: number
  endpoints: { origin: Place; destination: Place } | null
  onSelectRoute: (id: string) => void
}

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

function routeFeatures(plan: PlanResponse): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: plan.routes.flatMap((route) =>
      route.segments.map((segment) => ({
        type: 'Feature' as const,
        geometry: { type: 'LineString' as const, coordinates: segment.coordinates },
        properties: { routeId: route.id, level: segment.level },
      })),
    ),
  }
}

function checkpointFeatures(plan: PlanResponse): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: plan.routes.flatMap((route) =>
      route.checkpoints.map((cp) => ({
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [cp.lon, cp.lat] },
        properties: { routeId: route.id, index: cp.index, level: cp.level },
      })),
    ),
  }
}

/** One label per route at its midpoint; slots stagger them so overlapping routes stay readable. */
function labelFeatures(plan: PlanResponse): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: plan.routes.map((route, slot) => {
      const mid = route.checkpoints[Math.floor(route.checkpoints.length / 2)]
      return {
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [mid.lon, mid.lat] },
        properties: {
          routeId: route.id,
          slot,
          label: `${route.name} · ${formatDuration(route.duration_s)} · ${formatMiles(route.distance_miles)}`,
        },
      }
    }),
  }
}

function boundsOf(plan: PlanResponse): mapboxgl.LngLatBounds {
  const bounds = new mapboxgl.LngLatBounds()
  for (const route of plan.routes) for (const seg of route.segments) for (const c of seg.coordinates) bounds.extend(c)
  return bounds
}

function popupContent(route: Route, cp: Checkpoint): HTMLElement {
  const root = document.createElement('div')
  root.className = 'cp-popup'
  const add = (parent: HTMLElement, tag: string, text: string, className?: string) => {
    const el = document.createElement(tag)
    el.textContent = text
    if (className) el.className = className
    parent.appendChild(el)
    return el
  }
  add(root, 'h4', `${route.name} · mile ${cp.mile.toFixed(0)}`)
  add(root, 'p', `ETA ${formatTime(cp.eta, true)}`, 'muted')
  add(root, 'span', cp.level_label, 'pill').style.background = RISK_COLORS[cp.level]
  const w = cp.weather
  add(root, 'p', `Wind ${w.wind_mph} mph (gusts ${w.gust_mph})`)
  add(root, 'p', `Rain ${w.rain_in_hr} in/hr · Snow ${w.snow_in_hr} in/hr`)
  if (cp.reasons.length) {
    const list = add(root, 'ul', '')
    for (const reason of cp.reasons) add(list, 'li', reason)
  }
  if (cp.forecast_clamped) add(root, 'p', 'ETA is outside the forecast window; using the nearest available hour.', 'muted')
  return root
}

export function MapView({ plan, selectedId, heatmap, hour, endpoints, onSelectRoute }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const markersRef = useRef<mapboxgl.Marker[]>([])
  const planRef = useRef(plan)
  const onSelectRef = useRef(onSelectRoute)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    planRef.current = plan
    onSelectRef.current = onSelectRoute
  })

  // Create the map once and add all sources/layers up front; later updates only swap data.
  useEffect(() => {
    if (!TOKEN || !containerRef.current) return
    mapboxgl.accessToken = TOKEN
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: STYLE,
      center: [-98.5, 39.5],
      zoom: 3.4,
      attributionControl: true,
    })
    mapRef.current = map
    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right')

    map.on('load', () => {
      map.addSource('heat', { type: 'geojson', data: EMPTY })
      map.addSource('routes', { type: 'geojson', data: EMPTY })
      map.addSource('checkpoints', { type: 'geojson', data: EMPTY })
      map.addSource('labels', { type: 'geojson', data: EMPTY })

      map.addLayer({
        id: 'heat',
        type: 'heatmap',
        source: 'heat',
        paint: {
          'heatmap-weight': heatWeightExpression(0),
          'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 3, 0.5, 9, 1.2],
          'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 3, 14, 6, 45, 9, 110],
          'heatmap-color': HEAT_COLOR,
          'heatmap-opacity': 0.8,
        },
      })

      const line = { 'line-cap': 'round', 'line-join': 'round' } as const
      map.addLayer({
        id: 'routes-other',
        type: 'line',
        source: 'routes',
        filter: ['!=', ['get', 'routeId'], ''],
        layout: line,
        paint: { 'line-color': levelColorExpression() as Expr, 'line-width': 4, 'line-opacity': 0.45 },
      })
      map.addLayer({
        id: 'routes-casing',
        type: 'line',
        source: 'routes',
        filter: ['==', ['get', 'routeId'], ''],
        layout: line,
        paint: { 'line-color': '#ffffff', 'line-width': 9 },
      })
      map.addLayer({
        id: 'routes-selected',
        type: 'line',
        source: 'routes',
        filter: ['==', ['get', 'routeId'], ''],
        layout: line,
        paint: { 'line-color': levelColorExpression() as Expr, 'line-width': 5.5 },
      })

      const dotColor = levelColorExpression() as Expr
      map.addLayer({
        id: 'checkpoints-other',
        type: 'circle',
        source: 'checkpoints',
        filter: ['!=', ['get', 'routeId'], ''],
        paint: { 'circle-radius': 3, 'circle-color': dotColor, 'circle-opacity': 0.6 },
      })
      map.addLayer({
        id: 'checkpoints-selected',
        type: 'circle',
        source: 'checkpoints',
        filter: ['==', ['get', 'routeId'], ''],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 3.5, 8, 7],
          'circle-color': dotColor,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
        },
      })
      map.addLayer({
        id: 'route-labels',
        type: 'symbol',
        source: 'labels',
        layout: {
          'text-field': ['get', 'label'],
          'text-size': 12,
          'text-font': ['DIN Pro Medium', 'Arial Unicode MS Regular'],
          'text-allow-overlap': true,
          'text-offset': [
            'case',
            ['==', ['get', 'slot'], 0],
            ['literal', [0, -1.6]],
            ['==', ['get', 'slot'], 1],
            ['literal', [0, 0]],
            ['literal', [0, 1.6]],
          ],
        },
        paint: { 'text-color': '#1f2933', 'text-halo-color': '#ffffff', 'text-halo-width': 2 },
      })

      const select = (event: mapboxgl.MapMouseEvent) => {
        const hit = map.queryRenderedFeatures(event.point, { layers: ['checkpoints-selected', 'checkpoints-other', 'routes-other'] })[0]
        const routeId = hit?.properties?.routeId as string | undefined
        const current = planRef.current
        if (!hit || !routeId || !current) return
        const route = current.routes.find((r) => r.id === routeId)
        if (!route) return
        if (hit.layer?.id === 'checkpoints-selected') {
          const cp = route.checkpoints[hit.properties?.index as number]
          new mapboxgl.Popup({ offset: 10, maxWidth: '260px' })
            .setLngLat([cp.lon, cp.lat])
            .setDOMContent(popupContent(route, cp))
            .addTo(map)
        } else {
          onSelectRef.current(routeId)
        }
      }
      map.on('click', select)
      for (const layer of ['checkpoints-selected', 'checkpoints-other', 'routes-other']) {
        map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'))
        map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''))
      }
      setReady(true)
    })

    const observer = new ResizeObserver(() => map.resize())
    observer.observe(containerRef.current)
    return () => {
      observer.disconnect()
      map.remove()
      mapRef.current = null
      setReady(false)
    }
  }, [])

  // Route data, checkpoints, labels and the viewport follow the plan.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const set = (id: string, data: GeoJSON.FeatureCollection) => (map.getSource(id) as mapboxgl.GeoJSONSource).setData(data)
    set('routes', plan ? routeFeatures(plan) : EMPTY)
    set('checkpoints', plan ? checkpointFeatures(plan) : EMPTY)
    set('labels', plan ? labelFeatures(plan) : EMPTY)
    if (plan) map.fitBounds(boundsOf(plan), { padding: { top: 60, bottom: 60, left: 60, right: 60 }, duration: 800 })
  }, [plan, ready])

  // Selection only changes layer filters.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const is = ['==', ['get', 'routeId'], selectedId] as Expr
    const not = ['!=', ['get', 'routeId'], selectedId] as Expr
    map.setFilter('routes-selected', is)
    map.setFilter('routes-casing', is)
    map.setFilter('checkpoints-selected', is)
    map.setFilter('routes-other', not)
    map.setFilter('checkpoints-other', not)
  }, [selectedId, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    ;(map.getSource('heat') as mapboxgl.GeoJSONSource).setData(heatmap ? heatmap.points : EMPTY)
  }, [heatmap, ready])

  // The slider only swaps a paint expression: no data reload while dragging.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    map.setPaintProperty('heat', 'heatmap-weight', heatWeightExpression(hour))
  }, [hour, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    markersRef.current.forEach((marker) => marker.remove())
    markersRef.current = []
    if (!endpoints) return
    const pin = (place: Place, className: string, text: string) => {
      const el = document.createElement('div')
      el.className = `pin ${className}`
      el.textContent = text
      el.title = place.name
      markersRef.current.push(new mapboxgl.Marker({ element: el }).setLngLat([place.lon, place.lat]).addTo(map))
    }
    pin(endpoints.origin, 'start', 'Start')
    pin(endpoints.destination, 'end', 'End')
  }, [endpoints, ready])

  if (!TOKEN) {
    return (
      <div className="map-missing" role="alert">
        <p>
          The map needs a Mapbox public token. Set <code>VITE_MAPBOX_TOKEN</code> and rebuild the frontend.
        </p>
      </div>
    )
  }
  return <div ref={containerRef} className="map" aria-label="Route map" />
}
