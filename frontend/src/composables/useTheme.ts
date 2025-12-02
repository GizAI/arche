import { ref, watch, onMounted } from 'vue'

type Theme = 'light' | 'dark'

const theme = ref<Theme>('dark')
const STORAGE_KEY = 'arche-theme'

export function useTheme() {
  const setTheme = (newTheme: Theme) => {
    theme.value = newTheme
    document.documentElement.setAttribute('data-theme', newTheme)
    localStorage.setItem(STORAGE_KEY, newTheme)
  }

  const toggleTheme = () => {
    setTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  // Initialize theme from localStorage or system preference
  const initTheme = () => {
    const stored = localStorage.getItem(STORAGE_KEY) as Theme | null
    if (stored) {
      setTheme(stored)
    } else {
      // Check system preference
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      setTheme(prefersDark ? 'dark' : 'light')
    }
  }

  onMounted(() => {
    initTheme()
  })

  return {
    theme,
    setTheme,
    toggleTheme,
    initTheme,
  }
}
