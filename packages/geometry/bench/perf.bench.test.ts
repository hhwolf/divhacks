import { describe, expect, it } from 'vitest';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { validateLayout } from '../src/validate';

const root = join(__dirname, '..', '..', '..');
describe('perf: validation budget', () => {
  it('20 items validate in < 100 ms (p95 over 50 runs)', () => {
    const fx = JSON.parse(readFileSync(join(root, 'fixtures/validation/21-twenty-items-perf.json'), 'utf8'));
    const times: number[] = [];
    for (let i = 0; i < 50; i++) {
      const t = performance.now();
      validateLayout({ skeleton: fx.skeleton, furniture: fx.furniture, layout: fx.layout });
      times.push(performance.now() - t);
    }
    times.sort((a, b) => a - b);
    const p50 = times[24], p95 = times[47], max = times[49];
    mkdirSync(join(root, '.data'), { recursive: true });
    writeFileSync(join(root, '.data/bench-validation.json'), JSON.stringify({ items: fx.layout.items.length, runs: 50, p50, p95, max, at: new Date().toISOString() }, null, 2));
    console.log(`validation 20 items: p50=${p50.toFixed(2)}ms p95=${p95.toFixed(2)}ms max=${max.toFixed(2)}ms`);
    expect(p95).toBeLessThan(100);
  });
});
