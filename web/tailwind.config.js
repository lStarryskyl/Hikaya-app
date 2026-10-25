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
        muted: '#6D6457',
        muted2: '#6B6252',
        terracotta: {
          DEFAULT: '#9B4528',
          dark: '#8F3B1E',
          light: '#F3E2D6',
        },
        gold: {
          DEFAULT: '#79530F',
          light: '#F1E5C9',
        },
        teal: {
          DEFAULT: '#176650',
          light: '#DCEFE7',
        },
      },
      fontFamily: {
        serif: ['Fraunces Variable', 'ui-serif', 'Georgia', 'serif'],
        sans: ['Manrope Variable', 'system-ui', 'sans-serif'],
        arabic: ['"Noto Kufi Arabic Variable"', 'Manrope Variable', 'sans-serif'],
      },
      borderRadius: {
        xl2: '20px',
      },
    },
  },
  plugins: [],
}
