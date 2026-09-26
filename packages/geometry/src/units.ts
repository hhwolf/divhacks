import type { Units } from '@arp/contracts';
const IN = 0.0254;
/** 1.2192 → 4' 0" (imperial) or 1.22 m (metric). Values under 3 ft print as inches: 0.457 → 18 in. */
export function formatLength(m: number, units: Units = 'imperial'): string {
  if (units === 'metric') return m < 1 ? `${Math.round(m * 100)} cm` : `${(Math.round(m * 100) / 100).toFixed(2)} m`;
  const inches = m / IN;
  if (inches < 36) return `${Math.round(inches)} in`;
  const ft = Math.floor(inches / 12); const rem = Math.round(inches - ft * 12);
  return rem === 12 ? `${ft + 1}' 0"` : `${ft}' ${rem}"`;
}
export function formatDims(d: { w: number; d: number; h: number }, units: Units = 'imperial'): string {
  return `${formatLength(d.w, units)} × ${formatLength(d.d, units)} × ${formatLength(d.h, units)}`;
}
export function formatArea(m2: number, units: Units = 'imperial'): string {
  return units === 'metric' ? `${(Math.round(m2 * 10) / 10).toFixed(1)} m²` : `${Math.round(m2 * 10.7639)} sq ft`;
}
