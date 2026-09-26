import type { ValidationResult } from '@arp/contracts';
import { validateLayout, type ValidateInput } from './validate';

export function hashLayout(input: ValidateInput): string {
  const items = input.layout.items.map((i) => `${i.id}:${i.furnitureId}:${i.x.toFixed(3)}:${i.z.toFixed(3)}:${i.rotation}:${i.locked ? 1 : 0}`).join('|');
  const zones = (input.layout.zones ?? []).map((z) => `${z.label}:${z.x}:${z.z}:${z.w}:${z.d}`).join('|');
  const base = input.baseLayout ? input.baseLayout.items.filter((i) => i.locked).map((i) => `${i.id}:${i.x}:${i.z}:${i.rotation}`).join('|') : '';
  return `${input.skeleton.dimensions.l}x${input.skeleton.dimensions.w}#${items}#${zones}#${base}`;
}
const cache = new Map<string, ValidationResult>();
export function memoizedValidate(input: ValidateInput): ValidationResult {
  const h = hashLayout(input);
  const hit = cache.get(h); if (hit) return hit;
  const res = validateLayout(input);
  if (cache.size > 200) cache.delete(cache.keys().next().value!);
  cache.set(h, res);
  return res;
}
