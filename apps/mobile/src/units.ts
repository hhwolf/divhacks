import type { Units } from './types';

export const M_PER_FT = 0.3048;
export const M_PER_IN = 0.0254;

export function feetInchesToMeters(feet: number, inches: number): number {
  return feet * M_PER_FT + inches * M_PER_IN;
}

/** 3.4 m -> `11' 2"` (imperial) or `3.40 m` (metric). */
export function formatLength(meters: number, units: Units): string {
  if (!Number.isFinite(meters)) return '—';
  if (units === 'metric') return `${meters.toFixed(2)} m`;
  const totalInches = Math.round(meters / M_PER_IN);
  const ft = Math.floor(totalInches / 12);
  const inch = totalInches % 12;
  return inch === 0 ? `${ft}'` : `${ft}' ${inch}"`;
}

export function formatDims(dims: { l: number; w: number; h: number } | undefined, units: Units): string {
  if (!dims) return '—';
  return `${formatLength(dims.l, units)} × ${formatLength(dims.w, units)} × ${formatLength(dims.h, units)}`;
}

export function formatArea(l: number, w: number, units: Units): string {
  const m2 = l * w;
  if (units === 'metric') return `${m2.toFixed(1)} m²`;
  return `${Math.round(m2 / (M_PER_FT * M_PER_FT))} sq ft`;
}

/** Parses "3.4" / "3,4" into a number; returns NaN for garbage. */
export function parseNum(s: string): number {
  const t = s.trim().replace(',', '.');
  return t === '' ? NaN : Number(t);
}
