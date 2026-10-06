/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: 'rgb(var(--c-bg) / <alpha-value>)', surface: 'rgb(var(--c-surface) / <alpha-value>)', surface2: 'rgb(var(--c-surface-2) / <alpha-value>)', line: 'rgb(var(--c-line) / <alpha-value>)',
        fg: 'rgb(var(--c-fg) / <alpha-value>)', muted: 'rgb(var(--c-muted) / <alpha-value>)', brand: 'rgb(var(--c-brand) / <alpha-value>)', brandsoft: 'var(--brand-soft)',
        ok: 'rgb(var(--c-ok) / <alpha-value>)', warn: 'rgb(var(--c-warn) / <alpha-value>)', bad: 'rgb(var(--c-bad) / <alpha-value>)', info: 'rgb(var(--c-info) / <alpha-value>)',
      },
      fontFamily: { sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'] },
      boxShadow: { card: '0 1px 2px rgba(15,23,42,.05), 0 1px 3px rgba(15,23,42,.06)', pop: '0 12px 40px rgba(15,23,42,.18)' },
      borderRadius: { xl2: '14px' },
    },
  },
  plugins: [],
}
