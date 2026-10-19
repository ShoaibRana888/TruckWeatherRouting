import { formatTime } from '../format'

interface Props {
  start: string
  hours: number
  value: number
  departureHour: number
  onChange: (hour: number) => void
}

export function ForecastSlider({ start, hours, value, departureHour, onChange }: Props) {
  const when = new Date(new Date(start).getTime() + value * 3_600_000).toISOString()
  const max = hours - 1
  return (
    <div className="forecast-slider">
      <div className="forecast-head">
        <label htmlFor="forecast-hour">Weather heatmap</label>
        <output htmlFor="forecast-hour">
          {formatTime(when)} <span className="muted">({value === 0 ? 'now' : `+${value}h`})</span>
        </output>
      </div>
      <input
        id="forecast-hour"
        type="range"
        min={0}
        max={max}
        step={1}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <div className="forecast-foot">
        <span>Now</span>
        <button type="button" className="link" onClick={() => onChange(departureHour)}>
          Jump to departure
        </button>
        <span>+{max}h</span>
      </div>
    </div>
  )
}
