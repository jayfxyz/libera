/** Light or dark: follows the device unless this device chose one. index.html applies it before the first paint. */

export type ThemeChoice = 'system' | 'light' | 'dark'

const KEY = 'libera.theme'
const systemDark = window.matchMedia('(prefers-color-scheme: dark)')

export function themeChoice(): ThemeChoice {
  try {
    const saved = localStorage.getItem(KEY)
    return saved === 'light' || saved === 'dark' ? saved : 'system'
  } catch {
    return 'system'
  }
}

export function setThemeChoice(choice: ThemeChoice) {
  try {
    if (choice === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, choice)
  } catch {
    // Storage blocked: the choice lasts until the page reloads.
  }
  applyTheme(choice)
}

export function applyTheme(choice: ThemeChoice = themeChoice()) {
  const dark = choice === 'dark' || (choice === 'system' && systemDark.matches)
  document.documentElement.classList.toggle('dark', dark)
}

/** While on "system", follow the device switching between light and dark. */
export function followSystemTheme() {
  systemDark.addEventListener('change', onSystemChange)
}

function onSystemChange() {
  if (themeChoice() === 'system') applyTheme('system')
}
