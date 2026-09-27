import { create } from 'zustand';
import type { FurnishStyle, FurnitureItem, Layout, LayoutItem, Room, Rotation, Units, ValidationResult, Zone } from '@arp/contracts';
import { GRID, footprint, memoizedValidate, overlayMasks, roomBounds, type OverlayMasks } from '@arp/geometry';
import { api, unwrapLayout } from './lib/api';
import { isEmbedded, postToHost } from './lib/bridge';
import { thunk } from './lib/sound';

export type ViewMode = 'cutaway' | 'half' | 'plan';
export type Theme = 'stone' | 'peach' | 'teal';
export type FloorStyle = 'brick' | 'herringbone' | 'plank' | 'tile';
export type Drawer = null | 'menu' | 'paint' | 'help' | 'context';
export type SaveState = 'saved' | 'saving' | 'dirty' | 'blocked' | 'error' | 'readonly';
interface Snapshot { items: LayoutItem[]; zones: Zone[] }

export interface EditorState {
  embedded: boolean; units: Units; theme: Theme; night: boolean; sound: boolean; viewMode: ViewMode; orbit: 0 | 1 | 2 | 3;
  wallColor: string; floorStyle: FloorStyle; floorColor: string;
  room: Room | null; layouts: Layout[]; activeId: string | null; furniture: Record<string, FurnitureItem>; style: FurnishStyle | null; furnishing: boolean;
  /** drop-in animation after a furnish: start time + stagger index per new item id */
  entrance: { at: number; order: Record<string, number> } | null;
  items: LayoutItem[]; zones: Zone[]; history: Snapshot[]; future: Snapshot[];
  selectedId: string | null; placing: { furnitureId: string } | null; dragging: string | null; hoverId: string | null;
  overlays: { walkable: boolean; keepClear: boolean; lowClearance: boolean }; overlaysOpen: boolean; ghostId: string | null; ghostOpen: boolean;
  validation: ValidationResult | null; masks: OverlayMasks | null; saveState: SaveState; lastError: string | null;
  drawer: Drawer; contextTab: string | null; requestOpen: boolean; agentBusy: boolean; agentReply: string | null; analysisOpen: boolean;
  palettePage: number; category: string; search: string | null; sidePage: number; toasts: { id: number; text: string; kind: 'info' | 'error' }[];
  shake: string | null; bounce: string | null; loading: boolean;
  // actions
  init(opts: { units?: Units; embedded?: boolean }): void;
  loadLayout(id: string): Promise<void>;
  loadFixture(sample: string): Promise<void>;
  loadRoomLayouts(roomId: string): Promise<void>;
  switchLayout(id: string): Promise<void>;
  setItems(items: LayoutItem[], zones?: Zone[], pushHistory?: boolean): void;
  addItem(furnitureId: string, x?: number, z?: number): string;
  moveItem(id: string, x: number, z: number, opts?: { free?: boolean; commit?: boolean }): void;
  rotateItem(id: string): void; toggleLock(id: string): void; removeItem(id: string): void; duplicateItem(id: string): void; recolor(id: string, color: string | null): void;
  undo(): void; redo(): void; select(id: string | null): void; startPlacing(furnitureId: string): void; cancelPlacing(): void; setDragging(id: string | null): void; setHover(id: string | null): void;
  revalidate(): void; scheduleSave(): void; saveNow(): Promise<void>;
  setUnits(u: Units): void; setTheme(t: Theme): void; toggleNight(): void; toggleSound(): void; cycleView(): void; orbitBy(d: 1 | -1): void; setWallColor(c: string): void; setFloorStyle(s: FloorStyle, color?: string): void;
  toggleOverlay(k: keyof EditorState['overlays']): void; setOverlaysOpen(v: boolean): void; setGhost(id: string | null): void; setGhostOpen(v: boolean): void;
  setDrawer(d: Drawer, contextTab?: string | null): void; setRequestOpen(v: boolean): void; setAnalysisOpen(v: boolean): void;
  setPalettePage(p: number): void; setCategory(c: string): void; setSearch(s: string | null): void; setSidePage(p: number): void;
  createVariant(name?: string, fromId?: string): Promise<Layout | null>; renameVariant(id: string, name: string): Promise<void>; deleteVariant(id: string): Promise<void>;
  askAgent(text: string, furnitureId?: string): Promise<void>; furnish(theme: string, opts?: { restyle?: boolean; photos?: File[] }): Promise<void>; addFurniture(f: FurnitureItem): void;
  toast(text: string, kind?: 'info' | 'error'): void; dismissToast(id: number): void;
}

const snap = (v: number) => Math.round(v / GRID) * GRID;
export const ENTRANCE_STAGGER = 140; // ms between furnished pieces dropping in
const clone = (s: Snapshot): Snapshot => ({ items: s.items.map((i) => ({ ...i })), zones: s.zones.map((z) => ({ ...z })) });
let saveTimer: ReturnType<typeof setTimeout> | null = null;
let dragSnapshot: Snapshot | null = null; // items as they were when the current drag started (for a single undo step)
let toastId = 0;
const ls = <T,>(k: string, d: T): T => { try { const v = localStorage.getItem(k); return v ? (JSON.parse(v) as T) : d; } catch { return d; } };
const lsSet = (k: string, v: unknown) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ignore */ } };

export const useEditor = create<EditorState>((set, get) => ({
  embedded: false, units: ls('arp.units', 'imperial'), theme: ls('arp.theme', 'stone'), night: false, sound: false, viewMode: 'cutaway', orbit: 0,
  wallColor: ls('arp.wallColor', '#E6E1D8'), floorStyle: ls('arp.floorStyle', 'plank'), floorColor: ls('arp.floorColor', '#B39673'),
  room: null, layouts: [], activeId: null, furniture: {}, style: null, furnishing: false, entrance: null, items: [], zones: [], history: [], future: [],
  selectedId: null, placing: null, dragging: null, hoverId: null,
  overlays: { walkable: false, keepClear: false, lowClearance: false }, overlaysOpen: false, ghostId: null, ghostOpen: false,
  validation: null, masks: null, saveState: 'saved', lastError: null,
  drawer: null, contextTab: null, requestOpen: false, agentBusy: false, agentReply: null, analysisOpen: false,
  palettePage: 0, category: 'All', search: null, sidePage: 0, toasts: [], shake: null, bounce: null, loading: false,

  init({ units, embedded }) {
    set({ embedded: embedded ?? isEmbedded(), units: units ?? get().units, sound: !(embedded ?? isEmbedded()) && ls('arp.sound', true) });
  },
  async loadLayout(id) {
    set({ loading: true, lastError: null });
    try {
      const [res, catalog] = await Promise.all([api.layout(id), api.furniture().catch(() => [] as FurnitureItem[])]);
      const layout = res.layout;
      const room = res.room ?? (await api.room(layout.roomId)).room;
      const catalogItems = Array.isArray(catalog) ? catalog : catalog.items;
      const furniture = { ...get().furniture, ...Object.fromEntries(catalogItems.map((f) => [f.id, f])), ...(res.furniture ?? {}) };
      set({ room, activeId: layout.id, style: layout.style ?? null, items: layout.items.map((i) => ({ ...i })), zones: (layout.zones ?? []).map((z) => ({ ...z })), furniture, history: [], future: [], selectedId: null, placing: null, saveState: 'saved', loading: false });
      get().revalidate();
      void get().loadRoomLayouts(layout.roomId);
    } catch (e) { set({ loading: false, lastError: (e as Error).message }); get().toast(`Couldn't load layout: ${(e as Error).message}`, 'error'); }
  },
  async loadFixture(sample) {
    // Offline preview: room + Current Room built from fixtures/rooms/<sample>.json and the manifest (no API, no saving).
    set({ loading: true });
    const [fx, manifest] = await Promise.all([fetch(`/fixtures/rooms/sample-${sample}.json`).then((r) => r.json()), fetch('/assets/furniture/manifest.json').then((r) => r.json())]);
    const furniture = Object.fromEntries((manifest.items as FurnitureItem[]).map((m) => [m.id, m]));
    const room: Room = { id: `fixture-${sample}`, name: fx.name, skeleton: fx.skeleton, source: 'sample' };
    const items: LayoutItem[] = (fx.objects as LayoutItem[]).map((o, i) => ({ ...o, id: `${o.furnitureId}_${i + 1}` }));
    const layout: Layout = { id: 'fixture', roomId: room.id, name: 'Current Room', isCurrent: true, items, zones: [] };
    set({ room, furniture, layouts: [layout], activeId: 'fixture', style: null, items, zones: [], history: [], future: [], selectedId: null, saveState: 'readonly', loading: false });
    get().revalidate();
  },
  async loadRoomLayouts(roomId) {
    try { const r = await api.room(roomId); set({ layouts: r.layouts, room: r.room }); } catch { /* keep what we have */ }
  },
  async switchLayout(id) {
    if (id === get().activeId) return;
    if (get().saveState === 'dirty') await get().saveNow();
    history.replaceState(null, '', `/layout/${id}${location.search}`);
    await get().loadLayout(id);
    // tell the host which layout is now shown (it treats this as a replace, never a push)
    postToHost('editor:navigate', { route: `/layout/${id}`, replace: true });
  },
  setItems(items, zones, pushHistory = true) {
    const s = get();
    set({ items, zones: zones ?? s.zones, history: pushHistory ? [...s.history.slice(-60), clone({ items: s.items, zones: s.zones })] : s.history, future: pushHistory ? [] : s.future });
    get().revalidate(); get().scheduleSave();
  },
  addItem(furnitureId, x, z) {
    const s = get(); const f = s.furniture[furnitureId]; const room = s.room;
    if (!f || !room) return '';
    const b = roomBounds(room.skeleton);
    const n = s.items.filter((i) => i.furnitureId === furnitureId).length + 1;
    let id = `${furnitureId}_${n}`; while (s.items.some((i) => i.id === id)) id = `${id}b`;
    const item: LayoutItem = { id, furnitureId, x: snap(x ?? (b.x0 + b.x1) / 2), z: snap(z ?? (b.z0 + b.z1) / 2), rotation: 0, locked: false };
    s.setItems([...s.items, item]);
    set({ selectedId: id, bounce: id }); setTimeout(() => set({ bounce: null }), 400);
    if (get().sound) thunk();
    return id;
  },
  moveItem(id, x, z, opts) {
    const s = get(); const item = s.items.find((i) => i.id === id); const f = item && s.furniture[item.furnitureId]; const room = s.room;
    if (!item || !f || !room || item.locked) return;
    const b = roomBounds(room.skeleton); const { fx, fz } = footprint(f.dims, item.rotation);
    let nx = opts?.free ? x : snap(x), nz = opts?.free ? z : snap(z);
    // wall snap: within 15 cm of a wall → flush
    const SN = 0.15;
    if (!opts?.free) {
      if (Math.abs(nx - fx / 2 - b.x0) < SN) nx = b.x0 + fx / 2; if (Math.abs(b.x1 - (nx + fx / 2)) < SN) nx = b.x1 - fx / 2;
      if (Math.abs(nz - fz / 2 - b.z0) < SN) nz = b.z0 + fz / 2; if (Math.abs(b.z1 - (nz + fz / 2)) < SN) nz = b.z1 - fz / 2;
    }
    // clamp so the footprint stays inside the room bounds (bounds rule still catches polygon rooms)
    nx = Math.min(Math.max(nx, b.x0 + fx / 2), b.x1 - fx / 2); nz = Math.min(Math.max(nz, b.z0 + fz / 2), b.z1 - fz / 2);
    if (Math.abs(nx - item.x) < 1e-9 && Math.abs(nz - item.z) < 1e-9 && !opts?.commit) return;
    const items = s.items.map((i) => (i.id === id ? { ...i, x: +nx.toFixed(3), z: +nz.toFixed(3) } : i));
    if (opts?.commit) {
      const base = dragSnapshot ?? clone({ items: s.items, zones: s.zones }); dragSnapshot = null;
      const moved = base.items.some((b) => { const cur = items.find((i) => i.id === b.id); return !cur || Math.abs(cur.x - b.x) > 1e-9 || Math.abs(cur.z - b.z) > 1e-9; });
      if (moved) { set({ items, history: [...s.history.slice(-60), base], future: [] }); get().revalidate(); get().scheduleSave(); if (get().sound) thunk(); set({ bounce: id }); setTimeout(() => set({ bounce: null }), 350); }
      else set({ items });
    } else { set({ items }); get().revalidate(); }
  },
  rotateItem(id) {
    const s = get(); const item = s.items.find((i) => i.id === id); if (!item || item.locked) return;
    const rot = (((item.rotation + 90) % 360) as Rotation);
    s.setItems(s.items.map((i) => (i.id === id ? { ...i, rotation: rot } : i)));
    // keep inside bounds after rotating
    const f = s.furniture[item.furnitureId]; if (f) get().moveItem(id, item.x, item.z, { commit: false });
  },
  toggleLock(id) { const s = get(); s.setItems(s.items.map((i) => (i.id === id ? { ...i, locked: !i.locked } : i))); },
  removeItem(id) { const s = get(); const item = s.items.find((i) => i.id === id); if (!item || item.locked) { get().toast('Unlock it first'); return; } s.setItems(s.items.filter((i) => i.id !== id)); set({ selectedId: null }); },
  duplicateItem(id) { const s = get(); const item = s.items.find((i) => i.id === id); if (!item) return; const nid = s.addItem(item.furnitureId, item.x + 0.3, item.z + 0.3); if (nid) s.setItems(get().items.map((i) => (i.id === nid ? { ...i, rotation: item.rotation, color: item.color } : i)), undefined, false); },
  recolor(id, color) { const s = get(); s.setItems(s.items.map((i) => (i.id === id ? { ...i, color } : i))); },
  undo() { const s = get(); const prev = s.history[s.history.length - 1]; if (!prev) return; set({ history: s.history.slice(0, -1), future: [clone({ items: s.items, zones: s.zones }), ...s.future], items: prev.items, zones: prev.zones }); get().revalidate(); get().scheduleSave(); },
  redo() { const s = get(); const next = s.future[0]; if (!next) return; set({ future: s.future.slice(1), history: [...s.history, clone({ items: s.items, zones: s.zones })], items: next.items, zones: next.zones }); get().revalidate(); get().scheduleSave(); },
  select(id) { set({ selectedId: id, sidePage: 0 }); postToHost('editor:selection', { id }); },
  startPlacing(furnitureId) { set({ placing: { furnitureId }, selectedId: null }); },
  cancelPlacing() { set({ placing: null }); },
  setDragging(id) { if (id) dragSnapshot = clone({ items: get().items, zones: get().zones }); set({ dragging: id }); },
  setHover(id) { set({ hoverId: id }); },
  revalidate() {
    const s = get(); if (!s.room) return;
    const input = { skeleton: s.room.skeleton, furniture: s.furniture, layout: { items: s.items, zones: s.zones } };
    const t0 = performance.now();
    const validation = memoizedValidate(input);
    const masks = overlayMasks(input, validation);
    const dt = performance.now() - t0;
    if (dt > 100) console.warn(`validation took ${dt.toFixed(1)} ms`);
    const prevConf = s.validation?.metrics.conflicts ?? 0;
    set({ validation, masks });
    if (validation.metrics.conflicts > prevConf && s.dragging) { set({ shake: s.dragging }); setTimeout(() => set({ shake: null }), 400); }
    postToHost('editor:metrics', validation.metrics);
  },
  scheduleSave() {
    const s = get(); if (!s.activeId || s.activeId === 'fixture') return;
    if (s.validation?.blocked) { set({ saveState: 'blocked' }); return; }
    set({ saveState: 'dirty' });
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => void get().saveNow(), 600);
  },
  async saveNow() {
    const s = get(); if (!s.activeId) return;
    if (s.validation?.blocked) { set({ saveState: 'blocked' }); return; }
    set({ saveState: 'saving' });
    try {
      const res = await api.saveLayout(s.activeId, { items: s.items, zones: s.zones, source: 'editor' });
      const layout = unwrapLayout(res);
      set({ saveState: 'saved', layouts: get().layouts.map((l) => (l.id === layout.id ? layout : l)) });
      postToHost('editor:layoutChanged', { layoutId: layout.id, metrics: layout.metrics ?? get().validation?.metrics });
    } catch (e) { set({ saveState: 'error', lastError: (e as Error).message }); }
  },
  setUnits(units) { set({ units }); lsSet('arp.units', units); },
  setTheme(theme) { set({ theme }); lsSet('arp.theme', theme); },
  toggleNight() { set({ night: !get().night }); },
  toggleSound() { const v = !get().sound; set({ sound: v }); lsSet('arp.sound', v); if (v) thunk(); },
  cycleView() { const order: ViewMode[] = ['cutaway', 'half', 'plan']; set({ viewMode: order[(order.indexOf(get().viewMode) + 1) % 3] }); },
  orbitBy(d) { set({ orbit: (((get().orbit + d) % 4 + 4) % 4) as 0 | 1 | 2 | 3 }); },
  setWallColor(c) { set({ wallColor: c }); lsSet('arp.wallColor', c); },
  setFloorStyle(floorStyle, color) { set({ floorStyle, floorColor: color ?? get().floorColor }); lsSet('arp.floorStyle', floorStyle); if (color) lsSet('arp.floorColor', color); },
  toggleOverlay(k) { set({ overlays: { ...get().overlays, [k]: !get().overlays[k] } }); },
  setOverlaysOpen(v) { set({ overlaysOpen: v, ghostOpen: false }); },
  setGhost(id) { set({ ghostId: id }); },
  setGhostOpen(v) { set({ ghostOpen: v, overlaysOpen: false }); },
  setDrawer(d, contextTab = null) { set({ drawer: d, contextTab }); },
  setRequestOpen(v) { set({ requestOpen: v }); },
  setAnalysisOpen(v) { set({ analysisOpen: v }); },
  setPalettePage(p) { set({ palettePage: Math.max(0, p) }); },
  setCategory(c) { set({ category: c, palettePage: 0 }); },
  setSearch(s) { set({ search: s, palettePage: 0 }); },
  setSidePage(p) { set({ sidePage: Math.max(0, p) }); },
  async createVariant(name, fromId) {
    const s = get(); const base = fromId ?? s.activeId; if (!base) return null;
    try {
      const existing = s.layouts.map((l) => l.name);
      let n = name ?? `Variant ${s.layouts.length}`; let k = 2; const root = n; while (existing.includes(n)) n = `${root} (${k++})`;
      const layout = unwrapLayout(await api.fork(base, n));
      set({ layouts: [...s.layouts, layout] });
      await get().switchLayout(layout.id);
      return layout;
    } catch (e) { get().toast(`Couldn't create variant: ${(e as Error).message}`, 'error'); return null; }
  },
  async renameVariant(id, name) {
    const s = get(); const l = s.layouts.find((x) => x.id === id); if (!l || l.isCurrent) { get().toast('Current Room can’t be renamed'); return; }
    try { const res = unwrapLayout(await api.saveLayout(id, { name, source: 'editor' })); set({ layouts: s.layouts.map((x) => (x.id === id ? { ...x, name: res.name } : x)) }); }
    catch (e) { get().toast(`Rename failed: ${(e as Error).message}`, 'error'); }
  },
  async deleteVariant(id) {
    const s = get(); const l = s.layouts.find((x) => x.id === id); if (!l || l.isCurrent) { get().toast('Current Room can’t be deleted'); return; }
    try {
      await api.deleteLayout(id);
      const layouts = s.layouts.filter((x) => x.id !== id); set({ layouts });
      if (s.activeId === id) { const cur = layouts.find((x) => x.isCurrent) ?? layouts[0]; if (cur) await get().switchLayout(cur.id); }
    } catch (e) { get().toast(`Delete failed: ${(e as Error).message}`, 'error'); }
  },
  async askAgent(text, furnitureId) {
    const s = get(); if (!s.room || !s.activeId) return;
    set({ agentBusy: true, agentReply: null });
    try {
      const res = await api.agent({ text, roomId: s.room.id, baseLayoutId: s.activeId, furnitureId, channel: 'app' });
      set({ agentReply: res.reply, agentBusy: false });
      postToHost('editor:agentReply', { reply: res.reply, layoutId: res.layout?.id ?? null, status: res.status });
      if (res.layout) { await get().loadRoomLayouts(s.room.id); await get().switchLayout(res.layout.id); }
    } catch (e) { set({ agentBusy: false, agentReply: `Something went wrong: ${(e as Error).message}` }); }
  },
  async furnish(theme, opts) {
    // Theme → a new furnished variant (server picks pieces and places them), then open it and show what was made.
    // Restyle starts over from the Current Room (the real room) and keeps what the shown variant was for ("industrial" stays a bedroom).
    const s = get(); if (!s.room || !s.activeId || s.activeId === 'fixture' || s.furnishing) return;
    set({ furnishing: true });
    try {
      if (s.saveState === 'dirty') await s.saveNow();
      const active = s.layouts.find((l) => l.id === s.activeId);
      const base = opts?.restyle ? s.layouts.find((l) => l.isCurrent)?.id ?? s.activeId : s.activeId;
      const body = { theme, baseLayoutId: base, purposeHint: opts?.restyle ? active?.requestText ?? null : null };
      const res = opts?.photos?.length ? await api.furnishPhotos(s.room.id, opts.photos, body) : await api.furnish(s.room.id, body);
      set({ furnishing: false, agentReply: res.reply, requestOpen: true });
      postToHost('editor:agentReply', { reply: res.reply, layoutId: res.layout.id, status: 'ok' });
      // new pieces drop in one after another (anything that was already in the base stays put); armed before the switch so they never flash
      const kept = new Set((s.layouts.find((l) => l.id === base)?.items ?? []).map((i) => i.id));
      const order = Object.fromEntries(res.layout.items.filter((i) => !kept.has(i.id)).map((i, k) => [i.id, k]));
      set({ entrance: { at: Number.POSITIVE_INFINITY, order } });
      await get().loadRoomLayouts(s.room.id); await get().switchLayout(res.layout.id);
      set({ entrance: { at: performance.now(), order } }); setTimeout(() => set({ entrance: null }), 700 + Object.keys(order).length * ENTRANCE_STAGGER);
      if (get().sound) thunk();
    } catch (e) { set({ furnishing: false, entrance: null }); get().toast(`Couldn't furnish: ${(e as Error).message}`, 'error'); }
  },
  addFurniture(f) { set({ furniture: { ...get().furniture, [f.id]: f } }); },
  toast(text, kind = 'info') { const id = ++toastId; set({ toasts: [...get().toasts, { id, text, kind }] }); setTimeout(() => get().dismissToast(id), 3200); },
  dismissToast(id) { set({ toasts: get().toasts.filter((t) => t.id !== id) }); },
}));

/** Violations indexed by item id: 'error' beats 'warning'. */
export function violationLevel(v: ValidationResult | null, id: string): 'error' | 'warning' | null {
  if (!v) return null; let lvl: 'error' | 'warning' | null = null;
  for (const x of v.violations) if (x.items.includes(id)) { if (x.severity === 'error') return 'error'; lvl = 'warning'; }
  return lvl;
}

// Exposed for Playwright scripts (scripts/demo.py, scripts/screenshots.py) and debugging.
declare global { interface Window { __arpStore?: typeof useEditor } }
window.__arpStore = useEditor;
