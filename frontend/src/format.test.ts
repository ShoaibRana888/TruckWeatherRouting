import { describe, expect, it } from 'vitest'
import { defaultDeparture, formatDuration, formatMiles, hourOffset } from './format'

describe('formatDuration', () => {
  it('shows hours and zero-padded minutes', () => {
    expect(formatDuration(3 * 3600 + 5 * 60)).toBe('3h 05m')
  })
  it('drops hours when under one', () => {
    expect(formatDuration(42 * 60)).toBe('42m')
  })
  it('rounds to the nearest minute', () => {
    expect(formatDuration(89)).toBe('1m')
  })
})

describe('formatMiles', () => {
  it('keeps a decimal for short distances and rounds long ones', () => {
    expect(formatMiles(12.34)).toBe('12.3 mi')
    expect(formatMiles(412.6)).toBe('413 mi')
  })
})

describe('defaultDeparture', () => {
  it('is the next whole hour in local time', () => {
    const now = new Date(2026, 9, 19, 13, 40)
    expect(defaultDeparture(now)).toBe('2026-10-19T14:00')
  })
  it('rolls over midnight', () => {
    expect(defaultDeparture(new Date(2026, 9, 19, 23, 10))).toBe('2026-10-20T00:00')
  })
})

describe('hourOffset', () => {
  const start = '2026-10-19T12:00:00+00:00'
  it('counts whole forecast hours from the start', () => {
    expect(hourOffset(start, '2026-10-19T17:00:00+00:00', 48)).toBe(5)
  })
  it('rounds to the nearest hour', () => {
    expect(hourOffset(start, '2026-10-19T17:40:00+00:00', 48)).toBe(6)
  })
  it('clamps to the slider range', () => {
    expect(hourOffset(start, '2026-10-19T08:00:00+00:00', 48)).toBe(0)
    expect(hourOffset(start, '2026-10-29T08:00:00+00:00', 48)).toBe(48)
  })
})
