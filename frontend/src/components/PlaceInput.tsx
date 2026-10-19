import { useEffect, useId, useState } from 'react'
import { geocode } from '../api'
import { useDebounced } from '../hooks/useDebounced'
import type { Place } from '../types'

interface Props {
  label: string
  placeholder: string
  value: Place | null
  onChange: (place: Place | null) => void
}

/** Address autocomplete backed by the server's geocode proxy. */
export function PlaceInput({ label, placeholder, value, onChange }: Props) {
  const id = useId()
  const [text, setText] = useState(value?.name ?? '')
  const [result, setResult] = useState<{ query: string; places: Place[]; failed: boolean } | null>(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const query = useDebounced(text.trim(), 250)

  // Results only count while they belong to the current query and nothing is selected yet.
  const current = !value && result?.query === query ? result : null
  const options = current?.places ?? []
  const failed = current?.failed ?? false

  useEffect(() => {
    if (value || query.length < 2) return
    const controller = new AbortController()
    geocode(query, controller.signal)
      .then((places) => {
        setResult({ query, places, failed: false })
        setActive(-1)
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException)) setResult({ query, places: [], failed: true })
      })
    return () => controller.abort()
  }, [query, value])

  function choose(place: Place) {
    setText(place.name)
    setOpen(false)
    onChange(place)
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (!open || options.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((i) => (i + 1) % options.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((i) => (i <= 0 ? options.length - 1 : i - 1))
    } else if (event.key === 'Enter' && active >= 0) {
      event.preventDefault()
      choose(options[active])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="field place-input">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        autoComplete="off"
        placeholder={placeholder}
        value={text}
        role="combobox"
        aria-expanded={open && options.length > 0}
        aria-controls={`${id}-list`}
        aria-activedescendant={active >= 0 ? `${id}-opt-${active}` : undefined}
        aria-invalid={!value && text.length > 0 && !open ? true : undefined}
        onChange={(event) => {
          setText(event.target.value)
          setOpen(true)
          if (value) onChange(null)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
      />
      {open && options.length > 0 && (
        <ul id={`${id}-list`} className="suggestions" role="listbox">
          {options.map((place, i) => (
            <li
              key={`${place.lon},${place.lat}`}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : undefined}
              onMouseDown={(event) => {
                event.preventDefault()
                choose(place)
              }}
            >
              {place.name}
            </li>
          ))}
        </ul>
      )}
      {failed && <p className="hint error-text">Address search is unavailable right now.</p>}
      {!value && text.length > 0 && !open && !failed && (
        <p className="hint">Pick a suggestion from the list.</p>
      )}
    </div>
  )
}
