/** Audible marketplaces the login supports, with their flags. */
export const regions = [
  { value: 'us', label: 'United States' },
  { value: 'uk', label: 'United Kingdom' },
  { value: 'ca', label: 'Canada' },
  { value: 'de', label: 'Germany' },
  { value: 'fr', label: 'France' },
  { value: 'au', label: 'Australia' },
  { value: 'jp', label: 'Japan' },
  { value: 'in', label: 'India' },
  { value: 'es', label: 'Spain' },
  { value: 'it', label: 'Italy' },
  { value: 'br', label: 'Brazil' },
]

/** Flag emoji for an Audible locale ("uk" is the ISO code GB). */
export function flag(locale: string): string {
  const code = (locale === 'uk' ? 'gb' : locale).toUpperCase()
  if (!/^[A-Z]{2}$/.test(code)) return ''
  return String.fromCodePoint(...[...code].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65))
}

/** "🇬🇧 UK" */
export function regionBadge(locale: string): string {
  return `${flag(locale)} ${locale.toUpperCase()}`.trim()
}
