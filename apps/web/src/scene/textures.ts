import * as THREE from 'three';
import type { FloorStyle } from '../store';

const cache = new Map<string, THREE.Texture>();
function canvasTex(key: string, size: number, draw: (c: CanvasRenderingContext2D, s: number) => void, repeat = 1): THREE.Texture {
  const hit = cache.get(key); if (hit) return hit;
  const c = document.createElement('canvas'); c.width = c.height = size;
  draw(c.getContext('2d')!, size);
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(repeat, repeat); t.anisotropy = 4; t.colorSpace = THREE.SRGBColorSpace;
  cache.set(key, t); return t;
}
function shade(hex: string, amt: number): string {
  const c = new THREE.Color(hex); const hsl = { h: 0, s: 0, l: 0 }; c.getHSL(hsl); c.setHSL(hsl.h, hsl.s, Math.min(1, Math.max(0, hsl.l + amt))); return `#${c.getHexString()}`;
}

const rand = (i: number) => Math.abs(Math.sin(i * 12.9898 + 78.233) * 43758.5453) % 1;

/**
 * Draws one 1 m floor tile. `paint(i, x, y, w, h)` fills board/tile i; `seam` is the grout/joint fill. Shared by the
 * color map and the roughness map so both line up exactly.
 */
function drawFloor(ctx: CanvasRenderingContext2D, s: number, style: FloorStyle, seam: string, paint: (i: number, x: number, y: number, w: number, h: number) => void) {
  ctx.fillStyle = seam; ctx.fillRect(0, 0, s, s);
  if (style === 'brick') {
    const bw = s / 4, bh = s / 8, g = 5;
    for (let r = 0; r < 8; r++) for (let c = -1; c < 5; c++) paint(r * 7 + c, c * bw + (r % 2 ? bw / 2 : 0) + g / 2, r * bh + g / 2, bw - g, bh - g);
  } else if (style === 'herringbone') {
    const L = s / 4, W = s / 12, g = 3;
    ctx.save(); ctx.translate(s / 2, s / 2); ctx.rotate(Math.PI / 4); ctx.translate(-s, -s);
    for (let r = 0; r < 24; r++) for (let c = 0; c < 24; c++) {
      if ((r + c) % 2 === 0) paint(r * 13 + c, c * W, (r * L) / 3, W - g, L - g); else paint(r * 13 + c, c * W, (r * L) / 3, L - g, W - g);
    }
    ctx.restore();
  } else if (style === 'tile') {
    const n = 2, t = s / n, g = 3;
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) paint(r * 5 + c, c * t + g / 2, r * t + g / 2, t - g, t - g);
  } else {
    // one texture = 2 m: 12 boards of ~16 cm, each 1–2 m long with staggered butt joints
    const cols = 12, pw = s / cols, g = 2;
    for (let c = 0; c < cols; c++) {
      const segs = 1 + ((c * 7) % 3 === 0 ? 1 : 0) + (c % 2); const off = rand(c * 3.1) * s;
      for (let k = -1; k < segs; k++) { const y0 = (k / segs) * s + off % (s / segs); paint(c * 5 + k + 1, c * pw + g / 2, y0 + g / 2, pw - g, s / segs - g); }
    }
  }
}
/** Meters covered by one floor texture repeat for each style. */
export const FLOOR_TILE_M: Record<FloorStyle, number> = { plank: 2, herringbone: 1, brick: 1, tile: 1.2 };

/** Floor color texture, one repeat = FLOOR_TILE_M meters. Wood styles get per-board tone shifts and fine grain streaks. */
export function floorTexture(style: FloorStyle, base: string): THREE.Texture {
  const t = canvasTex(`floor:${style}:${base}`, 1024, (ctx, s) => {
    const wood = style === 'plank' || style === 'herringbone';
    drawFloor(ctx, s, style, shade(base, wood ? -0.14 : 0.12), (i, x, y, w, h) => {
      const r = rand(i); ctx.fillStyle = shade(base, (r - 0.5) * (wood ? 0.055 : 0.03)); roundRect(ctx, x, y, w, h, wood ? 1.5 : 3); ctx.fill();
      if (!wood) return;
      ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
      const alongX = w > h; const len = alongX ? w : h; const across = alongX ? h : w;
      for (let k = 0; k < across * 0.5; k++) {
        const t = rand(i * 31 + k) * across; const dark = rand(i * 7 + k * 3) > 0.5;
        ctx.strokeStyle = dark ? 'rgba(40,24,12,0.10)' : 'rgba(255,240,220,0.07)'; ctx.lineWidth = 0.6 + rand(k + i) * 1.2;
        ctx.beginPath();
        for (let u = 0; u <= len; u += len / 8) { const wob = Math.sin(u * 0.02 + k) * 1.8; if (alongX) ctx.lineTo(x + u, y + t + wob); else ctx.lineTo(x + t + wob, y + u); }
        ctx.stroke();
      }
      ctx.restore();
    });
  }, 1 / FLOOR_TILE_M[style]);
  return t;
}

/** Matching roughness map (green channel): boards vary slightly, joints and grout are matte. */
export function floorRoughness(style: FloorStyle): THREE.Texture {
  const t = canvasTex(`floor-rough:${style}`, 512, (ctx, s) => {
    const base = style === 'tile' ? 0.42 : style === 'brick' ? 0.8 : 0.58;
    drawFloor(ctx, s, style, '#f2f2f2', (i, x, y, w, h) => { const v = Math.round((base + (rand(i * 1.7) - 0.5) * 0.14) * 255); ctx.fillStyle = `rgb(${v},${v},${v})`; ctx.fillRect(x, y, w, h); });
  }, 1 / FLOOR_TILE_M[style]);
  t.colorSpace = THREE.NoColorSpace; return t;
}
function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
/** Soft radial blob for baked-looking ambient occlusion under items. */
export function aoTexture(): THREE.Texture {
  return canvasTex('ao', 128, (ctx, s) => {
    const g = ctx.createRadialGradient(s / 2, s / 2, s * 0.15, s / 2, s / 2, s / 2);
    g.addColorStop(0, 'rgba(34,28,24,0.42)'); g.addColorStop(0.55, 'rgba(34,28,24,0.16)'); g.addColorStop(1, 'rgba(34,28,24,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, s, s);
  });
}
/** Overlay mask → RGBA texture (nearest filtered). */
export function maskTexture(nx: number, nz: number, cells: { mask: Uint8Array; rgba: [number, number, number, number] }[]): THREE.DataTexture {
  const data = new Uint8Array(nx * nz * 4);
  for (const { mask, rgba } of cells) for (let k = 0; k < nx * nz; k++) if (mask[k]) { const o = k * 4; data[o] = rgba[0]; data[o + 1] = rgba[1]; data[o + 2] = rgba[2]; data[o + 3] = rgba[3]; }
  const t = new THREE.DataTexture(data, nx, nz, THREE.RGBAFormat); t.flipY = true; t.magFilter = THREE.NearestFilter; t.minFilter = THREE.NearestFilter; t.needsUpdate = true; t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
