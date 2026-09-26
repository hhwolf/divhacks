// Warm, cozy game-UI palette (matches the web editor's ref2 peach theme).
export const colors = {
  bg: '#D9A56E',
  bgDeep: '#C8935C',
  tile: '#F7F2EA',
  tileMuted: '#EFE6D8',
  ink: '#4A3327',
  inkSoft: '#7A5C4B',
  accent: '#8FBDB0',
  accentDeep: '#5F978A',
  danger: '#C75C4A',
  warn: '#E0B24A',
  white: '#FFFFFF',
} as const;

export const radius = { sm: 10, md: 12, lg: 16, pill: 999 } as const;

export const shadow = {
  soft: {
    shadowColor: '#4A3327',
    shadowOpacity: 0.18,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 3,
  },
} as const;

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 } as const;

export const type = {
  title: { fontSize: 28, fontWeight: '800' as const, color: colors.ink, letterSpacing: -0.5 },
  subtitle: { fontSize: 16, color: colors.inkSoft },
  h2: { fontSize: 18, fontWeight: '700' as const, color: colors.ink },
  body: { fontSize: 15, color: colors.ink },
  small: { fontSize: 13, color: colors.inkSoft },
} as const;
