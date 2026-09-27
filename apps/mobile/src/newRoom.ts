import loft from '../../../fixtures/rooms/sample-l-shaped.json';
import bedroom from '../../../fixtures/rooms/sample-nyc-bedroom.json';
import type { RoomDraft } from './types';

/** All sample entry points use the same goals-first flow as scans and manual dimensions. */
export function sampleRoomDraft(sample: 'l-shaped' | 'nyc-bedroom' = 'l-shaped'): RoomDraft {
  const data = sample === 'l-shaped' ? loft : bedroom;
  return { name: data.name, source: 'sample', sample, skeleton: data.skeleton as RoomDraft['skeleton'], objects: [] };
}
