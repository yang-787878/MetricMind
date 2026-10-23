import type { Config } from 'tailwindcss'

/**
 * 所有颜色都来自 src/styles/tokens.css 的 CSS 变量（rgb 三元组形式，便于用
 * `text-brand-500/40` 这类透明度写法）。这里不新增任何色值，只做映射。
 */
const rgb = (name: string) => `rgb(var(${name}-rgb) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: rgb('--bg'),
        surface: {
          DEFAULT: rgb('--surface'),
          2: rgb('--surface-2'),
          3: rgb('--surface-3'),
        },
        border: {
          DEFAULT: rgb('--border'),
          strong: rgb('--border-strong'),
        },
        ink: {
          DEFAULT: rgb('--text'),
          inverse: rgb('--text-inverse'),
        },
        secondary: rgb('--text-secondary'),
        muted: rgb('--text-muted'),
        brand: {
          50: rgb('--brand-50'),
          100: rgb('--brand-100'),
          500: rgb('--brand-500'),
          600: rgb('--brand-600'),
          700: rgb('--brand-700'),
        },
        success: { 50: rgb('--success-50'), 600: rgb('--success-600') },
        warning: { 50: rgb('--warning-50'), 600: rgb('--warning-600') },
        danger: { 50: rgb('--danger-50'), 600: rgb('--danger-600') },
        teal: { 50: rgb('--teal-50'), 600: rgb('--teal-600') },
        grid: rgb('--grid'),
        chart: {
          1: rgb('--chart-1'),
          2: rgb('--chart-2'),
          3: rgb('--chart-3'),
          4: rgb('--chart-4'),
          5: rgb('--chart-5'),
          6: rgb('--chart-6'),
        },
      },
      borderRadius: {
        sm: 'var(--r-sm)',
        DEFAULT: 'var(--r-md)',
        md: 'var(--r-md)',
        lg: 'var(--r-lg)',
        pill: 'var(--r-pill)',
      },
      boxShadow: {
        xs: 'var(--shadow-xs)',
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
      },
      fontSize: {
        // 只允许这 8 个字号，禁止 text-lg/text-xl 散用
        micro: ['11px', { lineHeight: '16px' }],
        caption: ['12px', { lineHeight: '18px' }],
        body: ['13px', { lineHeight: '20px' }],
        'body-lg': ['14px', { lineHeight: '22px' }],
        h4: ['16px', { lineHeight: '24px' }],
        h3: ['20px', { lineHeight: '28px' }],
        h2: ['24px', { lineHeight: '32px' }],
        h1: ['30px', { lineHeight: '38px' }],
      },
      maxWidth: {
        content: 'var(--content-max)',
        prose: '880px',
      },
      spacing: {
        rail: 'var(--rail-w)',
        'rail-collapsed': 'var(--rail-w-collapsed)',
        panel: 'var(--panel-w)',
      },
      transitionDuration: {
        DEFAULT: '150ms',
        200: '200ms',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
      animation: {
        'fade-in': 'fade-in 150ms ease-out',
      },
    },
  },
  plugins: [],
} satisfies Config
