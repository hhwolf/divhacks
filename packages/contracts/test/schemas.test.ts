import { describe, it, expect } from 'vitest';
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const root = join(__dirname, '..', '..', '..');
const load = (p: string) => JSON.parse(readFileSync(join(root, p), 'utf8'));

function ajv() {
  const a = new Ajv2020({ strict: false, allErrors: true });
  addFormats(a);
  for (const f of readdirSync(join(root, 'packages/contracts/schemas'))) a.addSchema(load(`packages/contracts/schemas/${f}`));
  return a;
}

describe('contracts', () => {
  it('sample rooms validate against skeleton schema', () => {
    const a = ajv();
    for (const f of readdirSync(join(root, 'fixtures/rooms')).filter((f) => f.endsWith('.json'))) {
      const room = load(`fixtures/rooms/${f}`);
      const ok = a.validate('https://roomplanner.dev/schemas/skeleton.schema.json', room.skeleton);
      expect(ok, `${f}: ${a.errorsText()}`).toBe(true);
    }
  });
  it('furniture manifest validates', () => {
    const a = ajv();
    const manifest = load('assets/furniture/manifest.json');
    for (const item of manifest.items) {
      const ok = a.validate('https://roomplanner.dev/schemas/furniture.schema.json', item);
      expect(ok, `${item.id}: ${a.errorsText()}`).toBe(true);
    }
  });
  it('mock plans validate against plan schema', () => {
    const a = ajv();
    for (const f of readdirSync(join(root, 'fixtures/plans')).filter((f) => f.endsWith('.json'))) {
      const ok = a.validate('https://roomplanner.dev/schemas/plan.schema.json', load(`fixtures/plans/${f}`));
      expect(ok, `${f}: ${a.errorsText()}`).toBe(true);
    }
  });
});
