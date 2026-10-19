import { useState } from 'react'
import { defaultDeparture } from '../format'
import type { Place, TripRequest } from '../types'
import { PlaceInput } from './PlaceInput'

const INTERVALS = [10, 25, 50] as const
const MAX_LOAD_LB = 80_000

interface Props {
  busy: boolean
  onSubmit: (trip: TripRequest, places: { origin: Place; destination: Place }) => void
}

export function TripForm({ busy, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(null)
  const [destination, setDestination] = useState<Place | null>(null)
  const [departure, setDeparture] = useState(defaultDeparture)
  const [load, setLoad] = useState('42000')
  const [interval, setInterval] = useState<TripRequest['interval_miles']>(25)

  const loadLb = Number(load)
  const loadValid = load !== '' && Number.isInteger(loadLb) && loadLb >= 0 && loadLb <= MAX_LOAD_LB
  const departureValid = departure !== '' && !Number.isNaN(new Date(departure).getTime())
  const canSubmit = origin && destination && loadValid && departureValid && !busy

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!origin || !destination || !canSubmit) return
    onSubmit(
      {
        origin: { lon: origin.lon, lat: origin.lat },
        destination: { lon: destination.lon, lat: destination.lat },
        departure_time: new Date(departure).toISOString(),
        load_weight_lb: loadLb,
        interval_miles: interval,
      },
      { origin, destination },
    )
  }

  return (
    <form className="trip-form" onSubmit={submit}>
      <PlaceInput label="Origin" placeholder="City or address" value={origin} onChange={setOrigin} />
      <PlaceInput label="Destination" placeholder="City or address" value={destination} onChange={setDestination} />

      <div className="row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input
            id="departure"
            type="datetime-local"
            value={departure}
            onChange={(event) => setDeparture(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="load">Load weight (lb)</label>
          <input
            id="load"
            type="number"
            inputMode="numeric"
            min={0}
            max={MAX_LOAD_LB}
            step={1000}
            value={load}
            aria-invalid={!loadValid}
            onChange={(event) => setLoad(event.target.value)}
          />
        </div>
      </div>
      {!loadValid && (
        <p className="hint error-text">Enter a whole number from 0 to {MAX_LOAD_LB.toLocaleString()} lb.</p>
      )}

      <fieldset className="field">
        <legend>Weather checkpoint every</legend>
        <div className="segmented" role="radiogroup">
          {INTERVALS.map((miles) => (
            <label key={miles} className={interval === miles ? 'selected' : undefined}>
              <input type="radio" name="interval" checked={interval === miles} onChange={() => setInterval(miles)} />
              {miles} mi
            </label>
          ))}
        </div>
      </fieldset>

      <button className="primary" type="submit" disabled={!canSubmit}>
        {busy ? 'Planning…' : 'Plan routes'}
      </button>
    </form>
  )
}
