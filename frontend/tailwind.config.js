/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: '#6C5CE7', soft: 'rgb(108 92 231 / 0.12)', dark: '#5A4BD1' },
        success: '#00B894',
        error: '#FF7675',
        accent: '#FDCB6E',
        bg: 'var(--bg)',
        card: 'var(--card)',
        ink: 'var(--text)',
        muted: 'var(--muted)',
        line: 'var(--line)',
        tint: 'var(--tint)',
        'tint-soft': 'var(--tint-soft)',
        'tint-ink': 'var(--tint-ink)',
      },
      fontFamily: {
        sans: ['Nunito', 'system-ui', 'sans-serif'],
        read: ['Inter', 'system-ui', 'sans-serif'],
      },
      borderRadius: { card: '18px', xl2: '20px' },
      boxShadow: {
        soft: '0 4px 18px -6px rgb(45 52 54 / 0.14)',
        lift: '0 10px 30px -10px rgb(45 52 54 / 0.25)',
      },
      keyframes: {
        shake: {
          '0%,100%': { transform: 'translateX(0)' },
          '20%': { transform: 'translateX(-7px)' },
          '40%': { transform: 'translateX(7px)' },
          '60%': { transform: 'translateX(-5px)' },
          '80%': { transform: 'translateX(5px)' },
        },
        pop: { '0%': { transform: 'scale(1)' }, '50%': { transform: 'scale(1.08)' }, '100%': { transform: 'scale(1)' } },
        shimmer: { '100%': { transform: 'translateX(100%)' } },
      },
      animation: {
        shake: 'shake 0.4s ease-in-out',
        pop: 'pop 0.3s ease-out',
      },
    },
  },
  plugins: [],
}
