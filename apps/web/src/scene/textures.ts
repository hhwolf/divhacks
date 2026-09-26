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

/** Floor material texture, one tile = 1 m. */
export function floorTexture(style: FloorStyle, base: string): THREE.Texture {
  return canvasTex(`floor:${style}:${base}`, 512, (ctx, s) => {
    ctx.fillStyle = shade(base, -0.09); ctx.fillRect(0, 0, s, s); // grout
    const tones = [base, shade(base, 0.04), shade(base, -0.04), shade(base, 0.08)];
    const pick = (i: number) => tones[Math.abs(Math.sin(i * 12.9898) * 43758.5453) % 1 > 0.5 ? (i % 3) : ((i + 1) % 4)];
    if (style === 'brick') {
      const bw = s / 4, bh = s / 8, g = 6;
      for (let r = 0; r < 8; r++) for (let c = -1; c < 5; c++) {
        const x = c * bw + (r % 2 ? bw / 2 : 0); ctx.fillStyle = pick(r * 7 + c); roundRect(ctx, x + g / 2, r * bh + g / 2, bw - g, bh - g, 6); ctx.fill();
      }
    } else if (style === 'herringbone') {
      const L = s / 4, W = s / 12, g = 4;
      ctx.save(); ctx.translate(s / 2, s / 2); ctx.rotate(Math.PI / 4); ctx.translate(-s, -s);
      for (let r = 0; r < 24; r++) for (let c = 0; c < 24; c++) {
        const vertical = (r + c) % 2 === 0; ctx.fillStyle = pick(r * 13 + c);
        if (vertical) roundRect(ctx, c * W * 1, r * L / 3, W - g, L - g, 3); else roundRect(ctx, c * W, r * L / 3, L - g, W - g, 3); ctx.fill();
      }
      ctx.restore();
    } else {
      const pw = s / 6, g = 4;
      for (let c = 0; c < 6; c++) { const segs = 2 + (c % 2); for (let k = 0; k < segs; k++) { const y0 = (k / segs) * s + (c % 2 ? s / (segs * 2) : 0); ctx.fillStyle = pick(c * 5 + k); roundRect(ctx, c * pw + g / 2, y0 + g / 2, pw - g, s / segs - g, 4); ctx.fill(); } }
    }
  }, 1);
}
function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
/** Soft radial blob for baked-looking ambient occlusion under items. */
export function aoTexture(): THREE.Texture {
  return canvasTex('ao', 128, (ctx, s) => {
    const g = ctx.createRadialGradient(s / 2, s / 2, s * 0.15, s / 2, s / 2, s / 2);
    g.addColorStop(0, 'rgba(60,30,15,0.55)'); g.addColorStop(0.6, 'rgba(60,30,15,0.25)'); g.addColorStop(1, 'rgba(60,30,15,0)');
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
