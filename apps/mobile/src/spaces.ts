// Post-scan setup vocabulary: what kind of space it is -> which elements it usually needs -> which catalog furniture
// (assets/furniture/manifest.json ids) the editor should suggest for it. Elements without furniture (e.g. "Open floor")
// are still saved on the room and passed to the planner as intent.

import type { IconName } from './components/ui';

export interface ElementDef { key: string; label: string; icon: IconName; furniture: string[] }
export interface SpaceTypeDef { key: string; label: string; icon: IconName; blurb: string; elements: string[] }

export const ELEMENTS: Record<string, ElementDef> = {
  bed: { key: 'bed', label: 'Bed', icon: 'bed-outline', furniture: ['bed_double'] },
  nightstand: { key: 'nightstand', label: 'Nightstand', icon: 'lamp-outline', furniture: ['nightstand'] },
  dresser: { key: 'dresser', label: 'Dresser', icon: 'dresser-outline', furniture: ['dresser'] },
  wardrobe: { key: 'wardrobe', label: 'Wardrobe', icon: 'wardrobe-outline', furniture: ['wardrobe'] },
  reading: { key: 'reading', label: 'Reading corner', icon: 'book-open-variant', furniture: ['armchair', 'floor_lamp', 'side_table'] },
  desk: { key: 'desk', label: 'Desk', icon: 'desk', furniture: ['desk'] },
  deskChair: { key: 'deskChair', label: 'Desk chair', icon: 'chair-rolling', furniture: ['chair_desk'] },
  bookshelf: { key: 'bookshelf', label: 'Bookshelf', icon: 'bookshelf', furniture: ['bookshelf'] },
  lamp: { key: 'lamp', label: 'Floor lamp', icon: 'floor-lamp-outline', furniture: ['floor_lamp'] },
  sofa: { key: 'sofa', label: 'Sofa', icon: 'sofa-outline', furniture: ['sofa'] },
  coffeeTable: { key: 'coffeeTable', label: 'Coffee table', icon: 'table-furniture', furniture: ['coffee_table'] },
  tv: { key: 'tv', label: 'TV / media', icon: 'television', furniture: ['tv_stand'] },
  armchair: { key: 'armchair', label: 'Armchair', icon: 'seat-outline', furniture: ['armchair'] },
  rug: { key: 'rug', label: 'Rug', icon: 'rug', furniture: ['rug'] },
  plant: { key: 'plant', label: 'Plants', icon: 'sprout-outline', furniture: ['plant'] },
  yoga: { key: 'yoga', label: 'Yoga zone', icon: 'yoga', furniture: ['yoga_mat'] },
  openFloor: { key: 'openFloor', label: 'Open floor', icon: 'vector-square', furniture: [] },
  gear: { key: 'gear', label: 'Gear storage', icon: 'package-variant-closed', furniture: ['bookshelf_low'] },
  worktable: { key: 'worktable', label: 'Worktable', icon: 'table-large', furniture: ['table'] },
  stool: { key: 'stool', label: 'Stool', icon: 'stool-outline', furniture: ['stool'] },
  shelving: { key: 'shelving', label: 'Open shelving', icon: 'bookshelf', furniture: ['bookshelf_low'] },
  twinBeds: { key: 'twinBeds', label: 'Two sleeping spots', icon: 'bed-single-outline', furniture: ['bed_single'] },
  splitStorage: { key: 'splitStorage', label: 'Split storage', icon: 'dresser-outline', furniture: ['dresser', 'wardrobe'] },
};

export const SPACE_TYPES: SpaceTypeDef[] = [
  { key: 'bedroom', label: 'Bedroom', icon: 'bed-outline', blurb: 'Sleep & get ready', elements: ['bed', 'nightstand', 'dresser', 'wardrobe', 'reading'] },
  { key: 'study', label: 'Study', icon: 'book-open-page-variant-outline', blurb: 'Work & focus', elements: ['desk', 'deskChair', 'bookshelf', 'lamp', 'reading'] },
  { key: 'living', label: 'Living Room', icon: 'sofa-outline', blurb: 'Lounge & host', elements: ['sofa', 'coffeeTable', 'tv', 'armchair', 'rug', 'plant'] },
  { key: 'workout', label: 'Workout', icon: 'yoga', blurb: 'Move & stretch', elements: ['yoga', 'openFloor', 'gear'] },
  { key: 'creative', label: 'Creative Studio', icon: 'palette-outline', blurb: 'Make things', elements: ['worktable', 'stool', 'shelving', 'openFloor', 'lamp'] },
  { key: 'shared', label: 'Shared Room', icon: 'account-multiple-outline', blurb: 'Two people, one room', elements: ['twinBeds', 'splitStorage', 'desk', 'nightstand'] },
];

/** Element keys suggested for the chosen space types, in first-seen order, without duplicates. */
export function suggestedElements(typeKeys: string[]): string[] {
  const out: string[] = [];
  for (const t of SPACE_TYPES) if (typeKeys.includes(t.key)) for (const e of t.elements) if (!out.includes(e)) out.push(e);
  return out;
}

/** Catalog ids to suggest in the editor for the chosen elements (custom elements match catalog words, e.g. "second desk"). */
export function furnitureFor(elementKeys: string[], custom: string[]): string[] {
  const ids = new Set<string>();
  for (const k of elementKeys) for (const f of ELEMENTS[k]?.furniture ?? []) ids.add(f);
  for (const label of custom) {
    const low = label.toLowerCase();
    for (const e of Object.values(ELEMENTS)) if (low.includes(e.label.toLowerCase().split(' ')[0])) e.furniture.forEach((f) => ids.add(f));
  }
  return [...ids];
}

export function typeLabel(key: string): string { return SPACE_TYPES.find((t) => t.key === key)?.label ?? key; }
