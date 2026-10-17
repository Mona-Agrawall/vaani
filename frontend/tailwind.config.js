// Colors come from CSS variables in src/index.css, so light and dark themes share one set of class names
const token = name => `rgb(var(--${name}) / <alpha-value>)`

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        bg: token('bg'),
        surface: token('surface'),
        sunken: token('sunken'),
        line: token('line'),
        fg: token('fg'),
        muted: token('muted'),
        faint: token('faint'),
        accent: token('accent'),
        success: token('success'),
        danger: token('danger'),
        ink: token('ink'),
        'on-ink': token('on-ink'),
      },
    },
  },
  plugins: [],
}
