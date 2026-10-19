import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, errorMessage, planTrip } from './api'
import type { TripRequest } from './types'

const trip: TripRequest = {
  origin: { lon: -97, lat: 32.8 },
  destination: { lon: -94, lat: 32.8 },
  departure_time: '2026-10-20T12:00:00Z',
  load_weight_lb: 40000,
  interval_miles: 25,
}

afterEach(() => vi.unstubAllGlobals())

function stubFetch(status: number, body: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })))
}

describe('errorMessage', () => {
  it('prefers the detail field', () => {
    expect(errorMessage({ detail: 'Weather service is unavailable.' }, 'x')).toBe('Weather service is unavailable.')
  })
  it('flattens validation errors', () => {
    expect(errorMessage({ load_weight_lb: ['Ensure this value is less than or equal to 80000.'] }, 'x')).toBe(
      'load weight lb: Ensure this value is less than or equal to 80000.',
    )
  })
  it('shows non-field errors without a prefix', () => {
    expect(errorMessage({ non_field_errors: ['Origin and destination are too close together.'] }, 'x')).toBe(
      'Origin and destination are too close together.',
    )
  })
  it('falls back for unknown bodies', () => {
    expect(errorMessage(null, 'fallback')).toBe('fallback')
  })
})

describe('planTrip', () => {
  it('returns the parsed body on success', async () => {
    stubFetch(200, { routes: [], recommended_route_id: 'A' })
    await expect(planTrip(trip)).resolves.toMatchObject({ recommended_route_id: 'A' })
  })
  it('throws an ApiError carrying the server message', async () => {
    stubFetch(502, { detail: 'Routing service is unavailable.' })
    await expect(planTrip(trip)).rejects.toMatchObject({ status: 502, message: 'Routing service is unavailable.' })
  })
  it('wraps network failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const error = await planTrip(trip).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(0)
  })
})
