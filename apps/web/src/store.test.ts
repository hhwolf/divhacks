/** Editor interactions (A3) exercised against the store with the sample room + manifest, no API. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { FurnitureItem, Room } from '@arp/contracts';
import { useEditor } from './store';

const root = join(__dirname, '..', '..', '..');
const bedroom = JSON.parse(readFileSync(join(root, 'fixtures/rooms/sample-nyc-bedroom.json'), 'utf8'));
const manifest = JSON.parse(readFileSync(join(root, 'assets/furniture/manifest.json'), 'utf8'));
const furniture: Record<string, FurnitureItem> = Object.fromEntries(manifest.items.map((m: FurnitureItem) => [m.id, m]));
const room: Room = { id: 'r1', name: bedroom.name, skeleton: bedroom.skeleton, source: 'sample' };

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ layout: { id: 'l1', roomId: 'r1', name: 'Current Room', isCurrent: true, items: useEditor.getState().items, zones: [] } }), { status: 200 })));
  useEditor.setState({
    room, furniture, activeId: 'l1', layouts: [], history: [], future: [], selectedId: null, placing: null, zones: [], validation: null, saveState: 'saved',
    items: bedroom.objects.map((o: { furnitureId: string; x: number; z: number; rotation: 0 | 90 | 180 | 270; locked: boolean }, i: number) => ({ id: `${o.furnitureId}_${i + 1}`, ...o })),
  });
  useEditor.getState().revalidate();
});

describe('editor store', () => {
  it('adds an item at the room centre and validates', () => {
    const id = useEditor.getState().addItem('desk');
    const it = useEditor.getState().items.find((i) => i.id === id)!;
    expect(it.x).toBeCloseTo(1.7, 5); expect(it.z).toBeCloseTo(1.5, 5);
    // centre of this room overlaps the bed → red; beside the window → clean
    expect(useEditor.getState().validation?.violations.some((v) => v.rule === 'overlap' && v.items.includes(id))).toBe(true);
    useEditor.getState().moveItem(id, 2.55, 0.3, { commit: true });
    expect(useEditor.getState().validation?.metrics.conflicts).toBe(0);
    expect(useEditor.getState().history.length).toBe(2);
  });
  it('drag snaps to the 10 cm grid, Shift free-moves', () => {
    const id = useEditor.getState().addItem('desk');
    useEditor.getState().moveItem(id, 1.234, 1.567, { commit: true });
    let it = useEditor.getState().items.find((i) => i.id === id)!;
    expect(it.x).toBeCloseTo(1.2, 9); expect(it.z).toBeCloseTo(1.6, 9);
    useEditor.getState().moveItem(id, 1.234, 1.567, { free: true, commit: true });
    it = useEditor.getState().items.find((i) => i.id === id)!;
    expect(it.x).toBeCloseTo(1.234, 9);
  });
  it('snaps flush to a wall when within 15 cm', () => {
    const id = useEditor.getState().addItem('desk'); // desk 1.2 × 0.6
    useEditor.getState().moveItem(id, 2.5, 0.4, { commit: true }); // z centre 0.4 → footprint z0 = 0.1 < 0.15 → flush to z=0
    const it = useEditor.getState().items.find((i) => i.id === id)!;
    expect(it.z).toBeCloseTo(0.3, 9);
  });
  it('R rotates 90° and swaps the footprint; locked items do not rotate or move', () => {
    const id = useEditor.getState().addItem('desk');
    useEditor.getState().rotateItem(id); expect(useEditor.getState().items.find((i) => i.id === id)!.rotation).toBe(90);
    const bed = useEditor.getState().items.find((i) => i.furnitureId === 'bed_double')!;
    expect(bed.locked).toBe(true);
    useEditor.getState().moveItem(bed.id, 2, 2, { commit: true }); useEditor.getState().rotateItem(bed.id);
    const after = useEditor.getState().items.find((i) => i.id === bed.id)!;
    expect([after.x, after.z, after.rotation]).toEqual([bed.x, bed.z, bed.rotation]);
  });
  it('lock toggles and remove refuses locked items', () => {
    const id = useEditor.getState().addItem('desk');
    useEditor.getState().toggleLock(id); expect(useEditor.getState().items.find((i) => i.id === id)!.locked).toBe(true);
    useEditor.getState().removeItem(id); expect(useEditor.getState().items.some((i) => i.id === id)).toBe(true);
    useEditor.getState().toggleLock(id); useEditor.getState().removeItem(id); expect(useEditor.getState().items.some((i) => i.id === id)).toBe(false);
  });
  it('undo / redo walk the history', () => {
    const n0 = useEditor.getState().items.length;
    const id = useEditor.getState().addItem('chair'); useEditor.getState().moveItem(id, 2.0, 2.0, { commit: true });
    useEditor.getState().undo(); expect(useEditor.getState().items.find((i) => i.id === id)!.x).toBeCloseTo(1.7, 5);
    useEditor.getState().undo(); expect(useEditor.getState().items.length).toBe(n0);
    useEditor.getState().redo(); useEditor.getState().redo(); expect(useEditor.getState().items.find((i) => i.id === id)!.x).toBeCloseTo(2.0, 5);
  });
  it('collision turns red and blocks saving; door swing is red but saveable', () => {
    const id = useEditor.getState().addItem('desk');
    useEditor.getState().moveItem(id, 2.9, 1.3, { commit: true }); // onto the dresser
    let v = useEditor.getState().validation!;
    expect(v.violations.some((x) => x.rule === 'overlap' && x.items.includes(id))).toBe(true); expect(v.blocked).toBe(true); expect(useEditor.getState().saveState).toBe('blocked');
    useEditor.getState().moveItem(id, 2.6, 2.4, { commit: true }); // into the door swing
    v = useEditor.getState().validation!;
    expect(v.violations.some((x) => x.rule === 'door_clearance' && x.items.includes(id))).toBe(true); expect(v.blocked).toBe(false);
  });
  it('duplicate copies rotation and offsets the copy', () => {
    const id = useEditor.getState().addItem('chair'); useEditor.getState().rotateItem(id);
    useEditor.getState().duplicateItem(id);
    const copies = useEditor.getState().items.filter((i) => i.furnitureId === 'chair');
    expect(copies.length).toBe(2); expect(copies[1].rotation).toBe(90);
  });
});
