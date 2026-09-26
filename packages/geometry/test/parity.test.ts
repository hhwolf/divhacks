import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { validateLayout } from '../src/validate';

const dir = join(__dirname, '..', '..', '..', 'fixtures', 'validation');
const files = readdirSync(dir).filter((f) => f.endsWith('.json')).sort();

describe('fixtures/validation parity (TS side)', () => {
  for (const f of files) {
    it(f, () => {
      const fx = JSON.parse(readFileSync(join(dir, f), 'utf8'));
      const res = validateLayout({ skeleton: fx.skeleton, furniture: fx.furniture, layout: fx.layout, baseLayout: fx.baseLayout ?? null });
      const got = res.violations.map((v) => `${v.rule}:${[...v.items].sort().join(',')}`).sort();
      const want = fx.expected.violations.map((v: { rule: string; items: string[] }) => `${v.rule}:${[...v.items].sort().join(',')}`).sort();
      expect(got).toEqual(want);
      for (const rule of fx.expectRules ?? []) expect(res.violations.some((v) => v.rule === rule), `rule ${rule} should fire`).toBe(true);
      expect(res.blocked).toBe(fx.expected.blocked);
      expect(res.metrics.conflicts).toBe(fx.expected.metrics.conflicts);
      expect(res.metrics.walkability).toBe(fx.expected.metrics.walkability);
      expect(Math.abs(res.metrics.openFloor - fx.expected.metrics.openFloor)).toBeLessThan(0.11);
      expect(Math.abs(res.metrics.reachableStorage - fx.expected.metrics.reachableStorage)).toBeLessThan(0.11);
      expect(Math.abs((res.metrics.largestFreeRect?.areaM2 ?? 0) - (fx.expected.metrics.largestFreeRect?.areaM2 ?? 0))).toBeLessThan(0.011);
      expect(res.metrics.largestFreeRect?.fits).toBe(fx.expected.metrics.largestFreeRect?.fits);
    });
  }
});
