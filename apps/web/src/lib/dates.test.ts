import { expect, it } from 'vitest';
import { nycDate } from './dates';

it('uses the NYC calendar for late-night observations and rental periods', () => {
  expect(nycDate(new Date('2026-09-27T02:00:00Z'))).toBe('2026-09-26');
  expect(nycDate(new Date('2026-10-01T02:00:00Z')).slice(0, 7)).toBe('2026-09');
  expect(nycDate(new Date('2026-01-01T04:30:00Z'))).toBe('2025-12-31');
});
