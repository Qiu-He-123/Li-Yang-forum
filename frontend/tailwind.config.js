/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        // ============ Apple HIG 设计令牌（Pinguo Design） ============
        // 品牌色阶
        brand: {
          50: '#e8f2ff',
          100: '#cfe5ff',
          200: '#9fcbff',
          300: '#66abff',
          400: '#2e8dff',
          500: '#007aff', // @primary
          600: '#0064d6',
          700: '#004fad',
          800: '#003b82',
          900: '#00275a',
        },
        // 背景色阶
        bg: {
          50: '#ffffff',
          100: '#f7f7fa',
          200: '#f2f2f7',
          300: '#e5e5ea',
          400: '#d1d1d6',
          500: '#aeaeb2',
          600: '#8e8e93',
          700: '#3a3a3c',
          800: '#1c1c1e',
          900: '#000000',
        },
        // 文字色阶
        text: {
          50: '#f5f5f7',
          100: '#e3e3e8',
          200: '#c7c7cc',
          300: '#aeaeb2',
          400: '#8e8e93',
          500: '#6e6e73',
          600: '#48484a',
          700: '#3c3c43',
          800: '#1d1d1f',
          900: '#000000',
        },
        // 功能色
        success: '#34c759',
        successSurface: '#e9f9ee',
        error: '#ff3b30',
        errorSurface: '#ffecea',
        warning: '#ff9500',
        warningSurface: '#fff4e6',
        // 辅助色（功能宫格分类色）
        chart: {
          1: '#007aff',
          2: '#ff3b30',
          3: '#ff9500',
          4: '#5856d6',
          5: '#af52de',
          6: '#34c759',
          7: '#00c7be',
        },
        // 保留旧令牌，避免历史引用断裂（admin 页面仍在用）
        ly: {
          ink: '#18222f',
          green: '#2d8f7b',
          blue: '#3867d6',
          paper: '#f5f6fa',
          line: '#ededf0',
        },
        tie: {
          blue: '#2e6be6',
          dark: '#1f56c4',
          deep: '#173fa3',
          light: '#e8f0ff',
          50: '#f2f6ff',
          100: '#e8f0ff',
          ink: '#1a1a1a',
          text: '#33373d',
          sub: '#8a9099',
          line: '#ededf0',
          paper: '#f5f6fa',
          fill: '#f7f8fa',
          orange: '#ff6633',
          gold: '#f5a623',
        },
      },
      fontFamily: {
        sans: ['DM Sans', 'Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Microsoft YaHei', 'sans-serif'],
      },
      borderRadius: {
        '4xl': '1.2rem',
        '3xl': '0.8rem',
        '2xl': '0.6rem',
      },
      boxShadow: {
        'hairline': '0 1px 2px -1px rgba(0,0,0,0.04)',
        'xs': '0 2px 4px -1px rgba(0,0,0,0.06), 0 1px 2px -1px rgba(0,0,0,0.04)',
        'sm': '0 4px 8px -2px rgba(0,0,0,0.08), 0 2px 4px -1px rgba(0,0,0,0.04)',
        'md': '0 8px 16px -4px rgba(0,0,0,0.08), 0 4px 8px -2px rgba(0,0,0,0.04)',
        'lg': '0 16px 32px -8px rgba(0,0,0,0.1), 0 8px 16px -4px rgba(0,0,0,0.04)',
        'xl': '0 24px 64px -12px rgba(0,0,0,0.12)',
      },
      transitionTimingFunction: {
        'apple': 'cubic-bezier(0.32, 0.72, 0, 1)',
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-apple',
        'slide-up': 'slideUp 0.3s ease-apple',
        'scale-in': 'scaleIn 0.2s ease-apple',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },
    },
  },
  plugins: [],
}
