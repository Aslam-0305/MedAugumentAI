/** Vibrant medical palette — teal/indigo accents on soft gradient backgrounds. */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#F0F4F8', panel: '#FFFFFF', ink: '#0F172A', muted: '#64748B', line: '#E2E8F0',
        primary: '#0D9488', primaryDark: '#0F766E', primarySoft: '#CCFBF1',
        accent: '#6366F1', accentDark: '#4F46E5', accentSoft: '#EEF2FF',
        original: '#64748B', augmented: '#6366F1', augmentedSoft: '#EEF2FF',
        lightbox: '#0F172A',
        ok: '#059669', okSoft: '#D1FAE5', warn: '#D97706', warnSoft: '#FEF3C7', bad: '#DC2626', badSoft: '#FEE2E2',
        sidebar: '#0F172A', sidebarMuted: '#94A3B8', sidebarHover: '#1E293B',
      },
      fontFamily: { sans: ['"Inter"', 'system-ui', 'sans-serif'] },
      boxShadow: {
        card: '0 1px 3px 0 rgb(0 0 0 / 0.06), 0 1px 2px -1px rgb(0 0 0 / 0.06)',
        elevated: '0 4px 6px -1px rgb(0 0 0 / 0.08), 0 2px 4px -2px rgb(0 0 0 / 0.06)',
        glow: '0 0 15px -3px rgb(13 148 136 / 0.3)',
        sidebar: '4px 0 15px 0 rgb(0 0 0 / 0.15)',
      },
      borderRadius: {
        xl: '0.75rem',
        '2xl': '1rem',
      },
      backgroundImage: {
        'gradient-brand': 'linear-gradient(135deg, #0D9488 0%, #6366F1 100%)',
        'gradient-card': 'linear-gradient(135deg, #F0FDFA 0%, #EEF2FF 100%)',
        'gradient-sidebar': 'linear-gradient(180deg, #0F172A 0%, #1E293B 100%)',
      },
    },
  },
  plugins: [],
}
