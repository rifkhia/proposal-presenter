const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
const UNITS = [
  ['year', 31536000],
  ['month', 2592000],
  ['week', 604800],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
]

// Backend timestamps are UTC; SQLite ones come without an offset.
const parse = (iso) => new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)

export function timeAgo(iso) {
  const seconds = (parse(iso).getTime() - Date.now()) / 1000
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit)
  }
  return 'just now'
}

export function fullDate(iso) {
  return parse(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}
