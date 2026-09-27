import * as THREE from 'three';

/**
 * Grounded PBR materials for the Kenney GLBs. Every Kenney model ships the same flat `wood` (orange) and `carpet` (coral)
 * materials, so each model gets its own palette here, keyed by GLB basename then Kenney material name. Colors are
 * muted real-world finishes (oak, walnut, linen, powder-coated steel…) so a room reads as mixed, lived-in furniture.
 */
export type Surface = 'wood' | 'fabric' | 'paint' | 'metal' | 'plastic' | 'ceramic' | 'leaf' | 'glass' | 'paper' | 'stone' | 'leather' | 'rubber' | 'shade';
export interface MatSpec { color: string; roughness: number; metalness?: number; surface: Surface; emissive?: string; emissiveIntensity?: number }

// Per-surface procedural variation: [frequency per local unit, roughness amplitude, tone amplitude, wood grain on/off].
const VARIATION: Record<Surface, [number, number, number, number]> = {
  wood: [4, 0.16, 0.14, 1], fabric: [22, 0.06, 0.06, 0], paint: [1.4, 0.1, 0.03, 0], metal: [9, 0.16, 0.04, 0],
  plastic: [7, 0.06, 0.03, 0], ceramic: [5, 0.1, 0.06, 0], leaf: [8, 0.12, 0.2, 0], glass: [2, 0.02, 0, 0],
  paper: [14, 0.05, 0.08, 0], stone: [6, 0.12, 0.08, 0], leather: [16, 0.16, 0.08, 0], rubber: [18, 0.06, 0.05, 0], shade: [12, 0.02, 0.03, 0],
};

const M = {
  // woods
  ash: { color: '#C2A887', roughness: 0.62, surface: 'wood' }, oak: { color: '#A98459', roughness: 0.6, surface: 'wood' },
  oakWarm: { color: '#9A7148', roughness: 0.58, surface: 'wood' }, walnut: { color: '#5E4333', roughness: 0.52, surface: 'wood' },
  birchPly: { color: '#D2BC98', roughness: 0.64, surface: 'wood' }, greyOak: { color: '#8E8173', roughness: 0.62, surface: 'wood' },
  ebonized: { color: '#2F2A27', roughness: 0.48, surface: 'wood' },
  // painted / laminate
  warmWhite: { color: '#E3DFD7', roughness: 0.5, surface: 'paint' }, offWhite: { color: '#D8D2C7', roughness: 0.55, surface: 'paint' },
  // metals & plastics
  blackSteel: { color: '#2B2C2E', roughness: 0.42, metalness: 0.75, surface: 'metal' }, steel: { color: '#A7ABAE', roughness: 0.32, metalness: 0.9, surface: 'metal' },
  brass: { color: '#A8844F', roughness: 0.36, metalness: 0.9, surface: 'metal' }, graphite: { color: '#3B3E42', roughness: 0.45, metalness: 0.15, surface: 'plastic' },
  enamel: { color: '#E6E6E2', roughness: 0.32, metalness: 0.05, surface: 'plastic' }, darkTrim: { color: '#3A3C3F', roughness: 0.4, metalness: 0.2, surface: 'plastic' },
  glass: { color: '#9FB2B8', roughness: 0.08, metalness: 0.2, surface: 'glass' },
  // fabrics & soft goods (tonal: greige, stone, mist — accents only a shade away from neutral)
  linen: { color: '#E7E2D8', roughness: 0.94, surface: 'fabric' }, oatmeal: { color: '#C9BDA9', roughness: 0.95, surface: 'fabric' },
  slateBlue: { color: '#848A92', roughness: 0.93, surface: 'fabric' }, sage: { color: '#8A8C80', roughness: 0.93, surface: 'fabric' },
  ochre: { color: '#B2A286', roughness: 0.92, surface: 'fabric' }, charcoal: { color: '#55565A', roughness: 0.92, surface: 'fabric' },
  stoneGrey: { color: '#8C8984', roughness: 0.94, surface: 'fabric' }, rugDark: { color: '#6B665D', roughness: 0.97, surface: 'fabric' },
  cognac: { color: '#7C4D31', roughness: 0.5, surface: 'leather' },
  // other
  terracotta: { color: '#B09A8A', roughness: 0.82, surface: 'ceramic' }, soil: { color: '#3B342E', roughness: 1, surface: 'paper' },
  leaf: { color: '#5E6B52', roughness: 0.7, surface: 'leaf' }, cardboard: { color: '#B8A184', roughness: 0.95, surface: 'paper' },
  tape: { color: '#A48760', roughness: 0.7, surface: 'paper' }, marble: { color: '#E3E0DA', roughness: 0.28, surface: 'stone' },
  mat: { color: '#7A8584', roughness: 0.8, surface: 'rubber' }, matDark: { color: '#5E6867', roughness: 0.82, surface: 'rubber' },
  shade: { color: '#EFE6D2', roughness: 0.9, surface: 'shade', emissive: '#FFE3B0', emissiveIntensity: 0.25 },
} satisfies Record<string, MatSpec>;

/** Fallback by Kenney material name, used for models without a palette entry. */
const BY_NAME: Record<string, MatSpec> = {
  wood: M.oak, woodDark: M.walnut, metal: M.steel, metalMedium: M.graphite, metalLight: M.enamel, metalDark: M.darkTrim,
  carpet: M.oatmeal, carpetWhite: M.linen, carpetDarker: M.charcoal, glass: M.glass, plant: M.leaf, lamp: M.shade, _defaultMat: M.warmWhite,
};

const PALETTES: Record<string, Record<string, MatSpec>> = {
  bed_double: { wood: M.ash, carpetWhite: M.linen, carpet: M.slateBlue, metal: M.blackSteel },
  bed_single: { wood: M.oakWarm, carpetWhite: M.linen, carpet: M.ochre, metal: M.blackSteel },
  bench: { wood: M.oak, carpet: M.oatmeal },
  bookshelf: { wood: M.birchPly },
  bookshelf_low: { wood: M.birchPly },
  chair: { wood: M.oakWarm },
  chair_desk: { metalMedium: M.graphite, carpet: M.charcoal },
  coffee_table: { wood: M.walnut },
  desk: { wood: M.oak, metal: M.blackSteel },
  dresser: { wood: M.warmWhite },
  floor_lamp: { metal: M.blackSteel, lamp: M.shade },
  mini_fridge: { metalLight: M.enamel, metalDark: M.darkTrim, glass: M.glass, metal: M.steel },
  moving_box: { wood: M.cardboard, woodDark: M.tape },
  nightstand: { wood: M.walnut, _defaultMat: { ...M.walnut, color: '#6B4C3A' }, metal: M.brass },
  plant: { wood: M.terracotta, woodDark: M.soil, plant: M.leaf },
  rug: { carpet: M.oatmeal, carpetDarker: M.rugDark },
  side_table: { wood: M.ebonized, _defaultMat: M.marble },
  sofa: { carpet: M.sage, wood: M.walnut },
  armchair: { carpet: M.ochre, wood: M.oak },
  stool: { wood: M.oak, carpet: M.cognac },
  table: { wood: M.ash },
  table_round: { wood: M.warmWhite },
  tv_stand: { wood: M.greyOak },
  wardrobe: { wood: M.offWhite, metal: M.steel },
  yoga_mat: { carpet: M.mat, carpetDarker: M.matDark },
};

/** `/assets/furniture/desk.glb` → `desk` (imported items reuse a preset GLB, so they inherit its palette). */
export function modelKey(url: string | null | undefined): string { return (url ?? '').split('/').pop()?.replace(/\.glb$/i, '') ?? ''; }

/**
 * Room styles from POST /rooms/{id}/furnish: one palette per Kenney material name, applied to every model so a furnished
 * room reads as one scheme. Models whose slots mean something else (plant pot/soil, cardboard box, fridge) keep their own.
 */
export type StyleId = 'japandi' | 'industrial' | 'boho' | 'minimal' | 'cozy';
const STYLES: Record<StyleId, Record<string, MatSpec>> = {
  japandi: { wood: M.ash, woodDark: M.walnut, carpet: M.oatmeal, carpetWhite: M.linen, carpetDarker: M.stoneGrey, metal: M.blackSteel, metalMedium: M.graphite, _defaultMat: M.birchPly },
  industrial: { wood: M.walnut, woodDark: M.ebonized, carpet: M.charcoal, carpetWhite: M.stoneGrey, carpetDarker: M.rugDark, metal: M.blackSteel, metalMedium: M.graphite, _defaultMat: M.greyOak },
  boho: {
    wood: M.oakWarm, woodDark: M.walnut, carpet: { color: '#B98A62', roughness: 0.93, surface: 'fabric' }, carpetWhite: M.oatmeal,
    carpetDarker: { color: '#8C5B42', roughness: 0.96, surface: 'fabric' }, metal: M.brass, _defaultMat: M.oakWarm,
  },
  minimal: { wood: M.warmWhite, woodDark: M.greyOak, carpet: { color: '#D6D2CB', roughness: 0.94, surface: 'fabric' }, carpetWhite: M.linen, carpetDarker: M.stoneGrey, metal: M.steel, _defaultMat: M.offWhite },
  cozy: { wood: M.oakWarm, woodDark: M.walnut, carpet: M.sage, carpetWhite: M.linen, carpetDarker: M.rugDark, metal: M.brass, _defaultMat: M.oak },
};
const STYLE_KEEP = new Set(['plant', 'moving_box', 'mini_fridge', 'floor_lamp', 'yoga_mat']);
/** Per-model accents on top of a style (upholstery only; bedding and rugs stay on the style's calmer fabrics). */
const STYLE_MODEL: Partial<Record<StyleId, Record<string, Record<string, MatSpec>>>> = {
  industrial: { sofa: { carpet: M.cognac }, armchair: { carpet: M.cognac }, stool: { carpet: M.cognac }, chair_desk: { carpet: M.charcoal } },
  boho: { sofa: { carpet: M.ochre }, bed_double: { carpet: M.ochre }, bed_single: { carpet: M.ochre } },
};

export function specFor(key: string, materialName: string, style?: StyleId | null): MatSpec {
  const styled = style && !STYLE_KEEP.has(key) ? STYLE_MODEL[style]?.[key]?.[materialName] ?? STYLES[style]?.[materialName] : undefined;
  return styled ?? PALETTES[key]?.[materialName] ?? BY_NAME[materialName] ?? M.oak;
}

/** Two dominant colors for the selection pill: the first non-metal finishes of the model's palette. */
export function swatchesFor(key: string): [string, string] | null {
  const p = PALETTES[key]; if (!p) return null;
  const cols = Object.values(p).filter((s) => s.surface !== 'metal' && s.surface !== 'glass').map((s) => s.color);
  const uniq = [...new Set(cols.map(tone))];
  return uniq.length ? [uniq[0], uniq[1] ?? tone(Object.values(p)[0].color)] : null;
}

/** Surfaces a user recolor applies to (metal hardware, glass and leaves keep their finish). */
export function recolorable(surface: Surface | undefined): boolean { return surface !== 'metal' && surface !== 'glass' && surface !== 'leaf'; }

/**
 * Scene-wide tonal grading: pulls saturation down and softens value contrast so every finish sits in one calm,
 * near-monochrome family (reads as a photographed apartment rather than a game palette). Applied to furniture and
 * to the room shell (walls, floor, trim, slab).
 */
export const TONE = { saturation: 0.55, contrast: 0.88 };
export function tone(hex: string): string {
  const c = new THREE.Color(hex); const hsl = { h: 0, s: 0, l: 0 }; c.getHSL(hsl);
  c.setHSL(hsl.h, hsl.s * TONE.saturation, 0.52 + (hsl.l - 0.52) * TONE.contrast);
  return `#${c.getHexString()}`;
}

export function makeMaterial(spec: MatSpec, name = ''): THREE.MeshStandardMaterial {
  const m = new THREE.MeshStandardMaterial({
    // smooth: the GLB's own normals decide (Kenney pieces ship split/flat normals, the Blender-built ones soft bevels)
    name, color: tone(spec.color), roughness: spec.roughness, metalness: spec.metalness ?? 0, flatShading: false,
    emissive: spec.emissive ?? '#000000', emissiveIntensity: spec.emissiveIntensity ?? 0,
  });
  m.userData.surface = spec.surface; m.userData.baseEmissive = m.emissive.clone(); m.userData.baseEmissiveIntensity = m.emissiveIntensity;
  patchSurface(m, spec.surface);
  return m;
}

const NOISE = /* glsl */ `
varying vec3 vArpP;
uniform float uArpFreq; uniform float uArpRough; uniform float uArpTone; uniform float uArpGrain;
float arpHash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float arpNoise(vec3 x) {
  vec3 i = floor(x); vec3 f = fract(x); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(arpHash(i), arpHash(i + vec3(1.0, 0.0, 0.0)), f.x), mix(arpHash(i + vec3(0.0, 1.0, 0.0)), arpHash(i + vec3(1.0, 1.0, 0.0)), f.x), f.y),
             mix(mix(arpHash(i + vec3(0.0, 0.0, 1.0)), arpHash(i + vec3(1.0, 0.0, 1.0)), f.x), mix(arpHash(i + vec3(0.0, 1.0, 1.0)), arpHash(i + vec3(1.0, 1.0, 1.0)), f.x), f.y), f.z);
}
float arpPattern() {
  vec3 p = vArpP * uArpFreq;
  float n = arpNoise(p) * 0.65 + arpNoise(p * 2.9 + 7.1) * 0.35;
  if (uArpGrain > 0.5) { float g = sin(vArpP.x * uArpFreq * 11.0 + vArpP.z * uArpFreq * 2.0 + n * 6.0) * 0.5 + 0.5; n = mix(n, g * g, 0.5); }
  return n;
}`;

/**
 * Adds subtle procedural roughness + tone variation in object space (so it doesn't swim while dragging): wood grain,
 * fabric weave noise, soft paint mottling. No UVs needed, which the Kenney GLBs don't carry textures for anyway.
 */
export function patchSurface(mat: THREE.MeshStandardMaterial, surface: Surface, freqScale = 1): void {
  const [freq, rough, tone, grain] = VARIATION[surface];
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uArpFreq = { value: freq * freqScale }; shader.uniforms.uArpRough = { value: rough };
    shader.uniforms.uArpTone = { value: tone }; shader.uniforms.uArpGrain = { value: grain };
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vArpP;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvArpP = position;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>\n${NOISE}`)
      .replace('#include <color_fragment>', '#include <color_fragment>\nfloat arpN = arpPattern();\ndiffuseColor.rgb *= 1.0 + (arpN - 0.5) * uArpTone;')
      .replace('#include <roughnessmap_fragment>', '#include <roughnessmap_fragment>\nroughnessFactor = clamp(roughnessFactor + (arpN - 0.5) * uArpRough, 0.04, 1.0);');
  };
  mat.customProgramCacheKey = () => 'arp-surface';
}
