/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        cream: '#F7F4EE',
        panel: '#FFFFFF',
        border: '#E7E0D3',
        ink: '#241F1A',
        ink2: '#3E362C',
        muted: '#8A8172',
        muted2: '#6B6252',
        terracotta: {
          DEFAULT: '#B85C38',
          dark: '#8F3B1E',
          light: '#F3E2D6',
        },
        gold: {
          DEFAULT: '#C08A2E',
          light: '#F1E5C9',
        },
        teal: {
          DEFAULT: '#1F7A63',
          light: '#DCEFE7',
        },
      },
      fontFamily: {
        serif: ['Fraunces', 'ui-serif', 'Georgia', 'serif'],
        sans: ['Manrope', 'system-ui', 'sans-serif'],
        arabic: ['"Noto Kufi Arabic"', 'Manrope', 'sans-serif'],
      },
      borderRadius: {
        xl2: '20px',
      },
    },
  },
  plugins: [],
}
