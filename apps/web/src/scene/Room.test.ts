import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { RoomSkeleton } from '@arp/contracts';
import { openingSpan } from '@arp/geometry';
import { wallLocalPointToWorld } from './Room';

const root = join(__dirname, '..', '..', '..', '..');
const loadSkeleton = (name: string): RoomSkeleton => JSON.parse(readFileSync(join(root, `fixtures/rooms/${name}.json`), 'utf8')).skeleton;

function expectPoint(actual: [number, number], expected: [number, number]) {
  expect(actual[0]).toBeCloseTo(expected[0], 6);
  expect(actual[1]).toBeCloseTo(expected[1], 6);
}

describe('room wall rendering coordinates', () => {
  it('keeps rendered door and window offsets aligned with canonical opening spans', () => {
    for (const sk of [loadSkeleton('sample-nyc-bedroom'), loadSkeleton('sample-studio')]) {
      for (const opening of [...sk.doors, ...sk.windows]) {
        const span = openingSpan(sk, opening);
        expectPoint(wallLocalPointToWorld(sk, opening.wall, opening.offset), span.a);
        expectPoint(wallLocalPointToWorld(sk, opening.wall, opening.offset + opening.width), span.b);
      }
    }
  });
});
