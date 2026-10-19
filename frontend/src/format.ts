export function formatDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return hours > 0 ? `${hours}h ${String(minutes).padStart(2, '0')}m` : `${minutes}m`
}

export function formatMiles(miles: number): string {
  return `${miles >= 100 ? Math.round(miles) : miles.toFixed(1)} mi`
}

export function formatTime(iso: string, withZone = false): string {
  return new Date(iso).toLocaleString([], {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
    ...(withZone ? { timeZoneName: 'short' } : {}),
  })
}

/** Value for a datetime-local input: the next whole hour, in the user's local time. */
export function defaultDeparture(now = new Date()): string {
  const next = new Date(now)
  next.setHours(next.getHours() + 1, 0, 0, 0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}T${pad(next.getHours())}:00`
}

/** Whole forecast hours from the heatmap's hour 0 to a time, clamped to the slider range. */
export function hourOffset(startIso: string, whenIso: string, maxHour: number): number {
  const hours = Math.round((new Date(whenIso).getTime() - new Date(startIso).getTime()) / 3_600_000)
  return Math.min(Math.max(hours, 0), maxHour)
}
