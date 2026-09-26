/**
 * Builds fixtures/validation/*.json from the scenario table below, computing `expected` with the TS validator
 * (TS is the source of truth; the Python port must reproduce these). Run: pnpm --filter @arp/geometry gen:expectations
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = fileURLToPath(new URL('.', import.meta.url));
import { validateLayout, type FurnitureLookup } from '../src/validate';
import type { LayoutItem, RoomSkeleton, Zone } from '@arp/contracts';

const root = join(__dirname, '..', '..', '..');
const manifest = JSON.parse(readFileSync(join(root, 'assets/furniture/manifest.json'), 'utf8'));
const FUR: FurnitureLookup = Object.fromEntries(manifest.items.map((m: { id: string; name: string; kind: string; dims: { w: number; d: number; h: number } }) => [m.id, { id: m.id, name: m.name, kind: m.kind, dims: m.dims }]));
const bedroom = JSON.parse(readFileSync(join(root, 'fixtures/rooms/sample-nyc-bedroom.json'), 'utf8'));
const studio = JSON.parse(readFileSync(join(root, 'fixtures/rooms/sample-studio.json'), 'utf8'));
const sk: RoomSkeleton = bedroom.skeleton;
const it = (id: string, furnitureId: string, x: number, z: number, rotation: 0 | 90 | 180 | 270 = 0, locked = false): LayoutItem => ({ id, furnitureId, x, z, rotation, locked });
const seed = (room: { objects: { furnitureId: string; x: number; z: number; rotation: number; locked: boolean }[] }): LayoutItem[] =>
  room.objects.map((o, i) => it(`${o.furnitureId}_${i + 1}`, o.furnitureId, o.x, o.z, o.rotation as 0 | 90 | 180 | 270, o.locked));
const pick = (ids: string[]): FurnitureLookup => Object.fromEntries(ids.map((id) => [id, FUR[id]]));

interface Scenario { name: string; description: string; expectRules: string[]; skeleton: RoomSkeleton; items: LayoutItem[]; zones?: Zone[]; baseLayout?: { items: LayoutItem[] } | null }
const scenarios: Scenario[] = [
  { name: '00-sample-bedroom-current', description: 'Seeded Current Room of the NYC sample bedroom: clean apart from nothing', expectRules: [], skeleton: sk, items: seed(bedroom) },
  { name: '01-sample-studio-current', description: 'Seeded Current Room of the studio sample', expectRules: [], skeleton: studio.skeleton, items: seed(studio) },
  { name: '10-bounds-desk-through-east-wall', description: 'Desk centered 20 cm from the east wall pokes through it', expectRules: ['bounds'], skeleton: sk, items: [...seed(bedroom), it('desk_1', 'desk', 3.2, 2.0)] },
  { name: '11-overlap-desk-on-dresser', description: 'Desk dropped on top of the dresser', expectRules: ['overlap'], skeleton: sk, items: [...seed(bedroom), it('desk_1', 'desk', 2.9, 1.3, 90)] },
  { name: '12-locked-bed-moved', description: 'Agent output moved the locked bed 30 cm', expectRules: ['locked'], skeleton: sk, items: seed(bedroom).map((i) => (i.furnitureId === 'bed_double' ? { ...i, x: i.x + 0.3 } : i)), baseLayout: { items: seed(bedroom) } },
  { name: '13-door-clearance-desk-in-swing', description: 'Desk parked in front of the door (the demo red state)', expectRules: ['door_clearance'], skeleton: sk, items: [...seed(bedroom), it('desk_1', 'desk', 2.6, 2.4)] },
  { name: '14-window-keep-clear-bookshelf', description: 'Tall bookshelf pushed against the window', expectRules: ['window_keep_clear'], skeleton: sk, items: [...seed(bedroom).filter((i) => i.furnitureId !== 'nightstand'), it('bookshelf_1', 'bookshelf', 1.6, 0.15)] },
  { name: '15-access-edge-bed-boxed-in', description: 'Wardrobe hard against the only free long edge of the bed', expectRules: ['access_edge'], skeleton: sk, items: [...seed(bedroom).filter((i) => i.furnitureId !== 'nightstand'), it('wardrobe_1', 'wardrobe', 1.7, 1.0, 90)] },
  { name: '16-access-edge-dresser-front-blocked', description: 'Bench parked right in front of the dresser', expectRules: ['access_edge'], skeleton: sk, items: [...seed(bedroom), it('bench_1', 'bench', 2.7, 1.3, 90)] },
  { name: '17-clear-zone-yoga-blocked', description: 'Requested 1.8 x 1.2 yoga zone overlaps the bookshelf', expectRules: ['clear_zone'], skeleton: sk, items: seed(bedroom), zones: [{ label: 'Yoga', x: 0.2, z: 1.7, w: 1.8, d: 1.2 }] },
  { name: '18-walkable-path-blocked-to-desk', description: 'Desk walled off in the NE corner by a wardrobe and dresser', expectRules: ['walkable_path'], skeleton: sk,
    items: [it('bed_1', 'bed_double', 0.7, 0.95, 0, true), it('desk_1', 'desk', 2.8, 0.3), it('wardrobe_1', 'wardrobe', 1.9, 0.5, 90), it('tv_1', 'tv_stand', 2.8, 0.8)] },
  { name: '19-marketplace-desk-fits', description: 'Demo happy path: 1.2 m desk beside the window, bed untouched', expectRules: [], skeleton: sk, items: [...seed(bedroom), it('desk_mkt', 'desk', 2.55, 0.3)], baseLayout: { items: seed(bedroom) } },
  { name: '20-floor-items-ignore-overlap', description: 'Rug under the bed and a yoga mat do not count as collisions', expectRules: [], skeleton: sk, items: [...seed(bedroom), it('rug_1', 'rug', 0.8, 1.2, 0), it('mat_1', 'yoga_mat', 2.0, 1.9)] },
  { name: '21-twenty-items-perf', description: '20 items, used by the perf bench', expectRules: [], skeleton: studio.skeleton,
    items: [
      it('a1', 'bed_single', 4.5, 0.95, 0, true), it('a2', 'sofa', 2.3, 3.15, 180), it('a3', 'coffee_table', 2.3, 2.1), it('a4', 'wardrobe', 4.7, 2.9, 270), it('a5', 'mini_fridge', 3.3, 0.25),
      it('a6', 'table_round', 3.4, 1.5), it('a7', 'chair', 2.65, 1.5, 90), it('a8', 'chair', 3.4, 2.25, 180), it('a9', 'desk', 1.2, 0.3), it('a10', 'chair_desk', 1.2, 0.9),
      it('a11', 'bookshelf', 0.15, 1.2, 90), it('a12', 'plant', 0.25, 0.25), it('a13', 'floor_lamp', 3.45, 3.4), it('a14', 'side_table', 1.15, 3.3), it('a15', 'stool', 0.9, 1.8),
      it('a16', 'moving_box', 4.75, 2.15), it('a17', 'moving_box', 4.25, 2.15), it('a18', 'rug', 2.3, 2.0, 90), it('a19', 'nightstand', 3.78, 0.2), it('a20', 'tv_stand', 2.4, 0.2),
    ] },
];

mkdirSync(join(root, 'fixtures/validation'), { recursive: true });
for (const s of scenarios) {
  const ids = [...new Set(s.items.map((i) => i.furnitureId))];
  const furniture = pick(ids);
  const layout = { items: s.items, zones: s.zones ?? [] };
  const res = validateLayout({ skeleton: s.skeleton, furniture, layout, baseLayout: s.baseLayout ?? null });
  for (const r of s.expectRules) if (!res.violations.some((v) => v.rule === r)) throw new Error(`${s.name}: expected rule ${r} did not fire. Got ${JSON.stringify(res.violations)}`);
  if (s.expectRules.length === 0 && res.violations.some((v) => v.severity === 'error')) console.warn(`${s.name}: unexpected errors`, res.violations);
  const fixture = { name: s.name, description: s.description, expectRules: s.expectRules, skeleton: s.skeleton, furniture, layout, baseLayout: s.baseLayout ?? null,
    expected: { violations: res.violations.map((v) => ({ rule: v.rule, items: [...v.items].sort(), message: v.message })), metrics: res.metrics, blocked: res.blocked } };
  writeFileSync(join(root, 'fixtures/validation', `${s.name}.json`), JSON.stringify(fixture, null, 1));
  console.log(s.name.padEnd(44), res.violations.map((v) => v.rule).join(',') || '-', '| open', res.metrics.openFloor, '| walk', res.metrics.walkability, '| lfr', res.metrics.largestFreeRect?.areaM2, res.metrics.largestFreeRect?.fits);
}
