/** @type {import('tailwindcss').Config} */
export default {
  // 使用 class 策略，避免 OS 深色模式误触发 dark: 变体
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {},
  },
  plugins: [],
}
