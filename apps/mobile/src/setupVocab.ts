// Local copy of apps/api/app/setup.py. Used when GET /setup/* is missing (older API) and to group
// suggested elements by the space type that suggested them. Keep in sync by hand.
import type { RoomElement, SpaceTypeInfo } from './types';
import type { IconName } from './components/ui';

export const SPACE_TYPES: SpaceTypeInfo[] = [
  { id: 'bedroom', label: 'Bedroom', icon: 'bed' },
  { id: 'study', label: 'Study', icon: 'desk' },
  { id: 'living', label: 'Living room', icon: 'sofa' },
  { id: 'workout', label: 'Workout', icon: 'yoga' },
  { id: 'creative', label: 'Creative studio', icon: 'palette' },
  { id: 'shared', label: 'Shared room', icon: 'people' },
];

/** The API's `icon` field is a generic hint; pick the MaterialCommunityIcons glyph by space-type id. */
export const SPACE_TYPE_ICONS: Record<string, IconName> = {
  bedroom: 'bed-king-outline',
  study: 'desk',
  living: 'sofa-outline',
  workout: 'yoga',
  creative: 'palette-outline',
  shared: 'account-group-outline',
};

export const ELEMENTS: RoomElement[] = [
  { id: 'bed', label: 'Bed', furnitureIds: ['bed_double', 'bed_single'] },
  { id: 'nightstand', label: 'Nightstand', furnitureIds: ['nightstand'] },
  { id: 'wardrobe', label: 'Wardrobe or dresser', furnitureIds: ['wardrobe', 'dresser'] },
  { id: 'desk', label: 'Desk and chair', furnitureIds: ['desk', 'chair_desk'] },
  { id: 'storage', label: 'Shelving / storage', furnitureIds: ['bookshelf', 'bookshelf_low'] },
  { id: 'reading', label: 'Reading corner', furnitureIds: ['armchair', 'floor_lamp', 'bookshelf_low'] },
  { id: 'sofa', label: 'Sofa', furnitureIds: ['sofa', 'armchair'] },
  { id: 'coffee_table', label: 'Coffee table', furnitureIds: ['coffee_table', 'side_table'] },
  { id: 'tv', label: 'TV stand', furnitureIds: ['tv_stand'] },
  { id: 'dining', label: 'Small dining table', furnitureIds: ['table_round', 'table', 'chair'] },
  { id: 'yoga', label: 'Yoga / workout zone', furnitureIds: ['yoga_mat'], zone: { w: 1.8, d: 1.2 } },
  { id: 'worktable', label: 'Work table', furnitureIds: ['table', 'stool'] },
  { id: 'plants', label: 'Plants', furnitureIds: ['plant'] },
  { id: 'rug', label: 'Rug', furnitureIds: ['rug'] },
  { id: 'second_bed', label: 'Second bed', furnitureIds: ['bed_single'] },
  { id: 'second_desk', label: 'Second desk', furnitureIds: ['desk', 'chair_desk'] },
  { id: 'mini_fridge', label: 'Mini fridge', furnitureIds: ['mini_fridge'] },
];

export const SUGGESTIONS: Record<string, string[]> = {
  bedroom: ['bed', 'nightstand', 'wardrobe', 'storage', 'rug'],
  study: ['desk', 'storage', 'reading', 'plants'],
  living: ['sofa', 'coffee_table', 'tv', 'rug', 'plants'],
  workout: ['yoga', 'storage'],
  creative: ['worktable', 'storage', 'plants', 'desk'],
  shared: ['second_bed', 'second_desk', 'wardrobe', 'mini_fridge'],
};

/** Mirrors `suggest_elements` in the API: union in space-type order, de-duplicated. */
export function localSuggestions(spaceTypes: string[]): { suggested: RoomElement[]; all: RoomElement[] } {
  const byId = new Map(ELEMENTS.map((e) => [e.id, e]));
  const seen = new Set<string>();
  const suggested: RoomElement[] = [];
  for (const st of spaceTypes) {
    for (const id of SUGGESTIONS[st] ?? []) {
      const el = byId.get(id);
      if (el && !seen.has(id)) {
        seen.add(id);
        suggested.push(el);
      }
    }
  }
  return { suggested, all: ELEMENTS };
}

export function slugify(label: string): string {
  return label
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}
