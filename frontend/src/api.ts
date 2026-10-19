import type { AppConfig, HeatmapResponse, Place, PlanResponse, TripRequest } from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

/** Flatten DRF validation errors ({field: [msg]}) or {detail} into one readable line. */
export function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>
    if (typeof record.detail === 'string') return record.detail
    const parts = Object.entries(record).map(([field, msgs]) => {
      const text = Array.isArray(msgs) ? msgs.join(' ') : String(msgs)
      return field === 'non_field_errors' ? text : `${field.replace(/_/g, ' ')}: ${text}`
    })
    if (parts.length) return parts.join('; ')
  }
  return fallback
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('Could not reach the server. Check your connection and try again.', 0)
  }
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(errorMessage(body, `Request failed (${response.status}).`), response.status)
  }
  return body as T
}

const post = <T>(path: string, payload: unknown, signal?: AbortSignal) =>
  request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })

export async function geocode(query: string, signal?: AbortSignal): Promise<Place[]> {
  const { results } = await request<{ results: Place[] }>(`/api/geocode/?q=${encodeURIComponent(query)}`, { signal })
  return results
}

export const planTrip = (trip: TripRequest, signal?: AbortSignal) => post<PlanResponse>('/api/plan/', trip, signal)

export const fetchHeatmap = (
  trip: Pick<TripRequest, 'origin' | 'destination' | 'load_weight_lb'>,
  signal?: AbortSignal,
) => post<HeatmapResponse>('/api/heatmap/', trip, signal)

export const getConfig = () => request<AppConfig>('/api/config/', {})
