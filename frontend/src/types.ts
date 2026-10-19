export interface LngLat {
  lon: number
  lat: number
}

export interface Place extends LngLat {
  name: string
}

/** 0 Low, 1 Moderate, 2 High, 3 Severe, 4 No Travel — matches the backend's RiskLevel. */
export type RiskLevel = 0 | 1 | 2 | 3 | 4

export interface TripRequest {
  origin: LngLat
  destination: LngLat
  departure_time: string
  load_weight_lb: number
  interval_miles: 10 | 25 | 50
}

export interface Weather {
  wind_mph: number
  gust_mph: number
  rain_in_hr: number
  snow_in_hr: number
}

export interface Checkpoint extends LngLat {
  index: number
  mile: number
  eta: string
  level: RiskLevel
  level_label: string
  weather: Weather
  reasons: string[]
  forecast_clamped: boolean
}

export interface Segment {
  level: RiskLevel
  coordinates: [number, number][]
}

export interface Route {
  id: string
  name: string
  summary: string
  rank: number
  recommended: boolean
  blocked: boolean
  distance_miles: number
  duration_s: number
  arrival_time: string
  metrics: {
    miles_by_level: Record<RiskLevel, number>
    avg_risk: number
  }
  segments: Segment[]
  checkpoints: Checkpoint[]
}

export interface PlanResponse {
  departure_time: string
  interval_miles: number
  load_weight_lb: number
  recommended_route_id: string
  recommendation: { explanation: string; all_blocked: boolean }
  routes: Route[]
}

export interface HeatmapResponse {
  /** ISO time of forecast hour 0 (the current hour, UTC). */
  start: string
  hours: number
  max_level: number
  points: GeoJSON.FeatureCollection<GeoJSON.Point, Record<`r${number}`, number>>
}

export interface AppConfig {
  mapbox_token: string
  map_style: string
}
