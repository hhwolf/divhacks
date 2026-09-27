// Calm botanical palette: deep forest + olive + sage greens on a warm off-white (tonal, one hue family, white type on green).
export const colors = {
  bg: '#F3F4EF',
  bgDeep: '#E6E9DF',
  tile: '#FFFFFF',
  tileMuted: '#E3E7DA',
  ink: '#253420',
  inkSoft: '#667360',
  accent: '#8BA36E',
  accentDeep: '#5B7640',
  forest: '#3E5A2B',
  sageTint: '#DCE5D0',
  danger: '#B4533F',
  warn: '#C7A24C',
  white: '#FFFFFF',
} as const;

export const radius = { sm: 10, md: 14, lg: 20, pill: 999 } as const;

export const shadow = {
  soft: {
    shadowColor: '#253420',
    shadowOpacity: 0.08,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 6 },
    elevation: 2,
  },
} as const;

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 } as const;

export const type = {
  title: { fontSize: 30, fontWeight: '700' as const, color: colors.ink, letterSpacing: -0.6 },
  subtitle: { fontSize: 15, color: colors.inkSoft, lineHeight: 21 },
  h2: { fontSize: 18, fontWeight: '700' as const, color: colors.ink, letterSpacing: -0.2 },
  body: { fontSize: 15, color: colors.ink },
  small: { fontSize: 13, color: colors.inkSoft },
  eyebrow: { fontSize: 12, fontWeight: '700' as const, color: colors.accentDeep, letterSpacing: 1.2, textTransform: 'uppercase' as const },
} as const;
