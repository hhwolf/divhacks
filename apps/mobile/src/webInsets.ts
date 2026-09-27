// Web-only safe-area override for the /device phone-frame preview (apps/web/src/ui/DevicePreview.tsx).
// A browser reports zero safe-area insets, so screens would sit under the simulated Dynamic Island. The preview passes
// `?insets=top,right,bottom,left` (points); it is kept in sessionStorage so it survives in-app navigation. Native: null.

import { Platform } from 'react-native';

export interface Insets { top: number; right: number; bottom: number; left: number }

export function webInsetsOverride(): Insets | null {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return null;
  let raw: string | null = null;
  try {
    raw = new URLSearchParams(window.location.search).get('insets');
    if (raw) sessionStorage.setItem('arp.insets', raw);
    else raw = sessionStorage.getItem('arp.insets');
  } catch {
    return null;
  }
  if (!raw) return null;
  const [top = 0, right = 0, bottom = 0, left = 0] = raw.split(',').map(Number);
  return [top, right, bottom, left].every(Number.isFinite) ? { top, right, bottom, left } : null;
}
