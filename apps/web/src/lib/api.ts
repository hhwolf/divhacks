import { sessionHeaders } from './auth';

import type { FurnishStyle, FurnitureItem, HousingProfile, Layout, PaymentQuote, PaymentRecord, QuoteRequest, Tenancy, EvidencePhoto, AddressCandidate, SourceInfo, RentalComparable, RentAssessment, Room, ValidationResult } from '@arp/contracts';

const nativeApi = (window as unknown as { __ARP_NATIVE_API_URL?: string }).__ARP_NATIVE_API_URL;
/** In development, a page opened from another device (http://<this Mac's LAN IP>:5173) must call the API on that same host, not the device's own localhost. */
function devApi(configured: string): string {
  if (!import.meta.env.DEV || typeof window === 'undefined') return configured;
  const api = new URL(configured); const page = window.location.hostname;
  return ['localhost', '127.0.0.1'].includes(api.hostname) && !['localhost', '127.0.0.1', ''].includes(page) ? `${api.protocol}//${page}:${api.port || '8000'}` : configured;
}
let base = nativeApi ?? devApi((import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000');
export function setApiBase(url: string) {
  const target = new URL(url); const configured = new URL(devApi((import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'));
  const local = ['localhost', '127.0.0.1'].includes(target.hostname);
  if (target.origin !== configured.origin && target.origin !== (nativeApi ? new URL(nativeApi).origin : null) && !(import.meta.env.DEV && local)) throw new Error('Untrusted API origin');
  base = target.origin;
}
export function apiBase() { return base; }

export async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(await sessionHeaders()), ...(init?.headers ?? {}) } });
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j); } catch { /* ignore */ }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.status === 204 ? undefined as T : res.json() as Promise<T>;
}

export interface LayoutResponse { layout: Layout; furniture: Record<string, FurnitureItem>; validation?: ValidationResult; room?: Room }
export interface RoomResponse { room: Room; layouts: Layout[]; currentLayout?: Layout }
/** One arrangement the interior designer saved as a variant (references/options-output.md in the skill). */
export interface AgentOption { variantName: string; layoutId: string; recommended: boolean; moved: string[]; explanation?: string | null; tradeoff: string; validation: { ok: boolean; warnings: number; openFloorPct: number }; skillValidation: { ok: boolean; warnings: number; open_floor_pct: number } }
export interface AgentResponse { plan: unknown; layout: Layout | null; reply: string; status: string; links?: string[]; requestId?: string; options?: AgentOption[]; recommended?: string | null; roomSummary?: string | null }
export interface FurnishResponse { layout: Layout; style: FurnishStyle; placed: string[]; skipped: string[]; reply: string }
export interface RentAssessBody extends HousingProfile { layoutId?: string | null }
export interface CompareResponse {
  a: Layout; b: Layout;
  deltas: { openFloor: number; conflicts: number; reachableStorage: number; largestFreeRectArea: number };
  moved: { id: string; name: string; from: { x: number; z: number; rotation: number }; to: { x: number; z: number; rotation: number } }[];
  added: { id: string; name: string }[]; removed: { id: string; name: string }[];
}

export const api = {
  health: () => req<{ status: string; mode: string; integrations: Record<string, string> }>('/health'),
  createRoom: (body: unknown) => req<RoomResponse>('/rooms', { method: 'POST', body: JSON.stringify(body) }),
  rooms: () => req<Room[]>('/rooms'),
  room: (id: string) => req<RoomResponse>(`/rooms/${id}`),
  layout: (id: string) => req<LayoutResponse>(`/layouts/${id}`),
  saveLayout: (id: string, body: Partial<Layout> & { source: 'editor' }) => req<LayoutResponse>(`/layouts/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  fork: (id: string, name?: string) => req<LayoutResponse | Layout>(`/layouts/${id}/fork`, { method: 'POST', body: JSON.stringify({ name }) }),
  deleteLayout: (id: string) => req<unknown>(`/layouts/${id}`, { method: 'DELETE' }),
  compare: (a: string, b: string) => req<CompareResponse>(`/layouts/${a}/compare/${b}`),
  furniture: () => req<{ items: FurnitureItem[] } | FurnitureItem[]>('/furniture'),
  fromLink: (url: string) => req<FurnitureItem | { item: FurnitureItem }>('/furniture/from-link', { method: 'POST', body: JSON.stringify({ url }) }),
  fromPhoto: async (file: File) => {
    const fd = new FormData(); fd.append('image', file);
    const res = await fetch(`${base}/furniture/from-photo`, { method: 'POST', body: fd, headers: await sessionHeaders() });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json() as Promise<FurnitureItem | { item: FurnitureItem }>;
  },
  furnish: (roomId: string, body: { theme: string; baseLayoutId?: string; purposeHint?: string | null }) => req<FurnishResponse>(`/rooms/${roomId}/furnish`, { method: 'POST', body: JSON.stringify(body) }),
  furnishPhotos: async (roomId: string, photos: File[], body: { theme?: string; baseLayoutId?: string; purposeHint?: string | null }) => {
    const fd = new FormData(); photos.forEach((p) => fd.append('images', p));
    if (body.theme) fd.append('theme', body.theme); if (body.baseLayoutId) fd.append('baseLayoutId', body.baseLayoutId); if (body.purposeHint) fd.append('purposeHint', body.purposeHint);
    const res = await fetch(`${base}/rooms/${roomId}/furnish/photos`, { method: 'POST', headers: await sessionHeaders(), body: fd });
    if (!res.ok) { let d = res.statusText; try { const j = await res.json(); d = typeof j.detail === 'string' ? j.detail : d; } catch { /* ignore */ } throw new Error(`${res.status} ${d}`); }
    return res.json() as Promise<FurnishResponse>;
  },
  agent: (body: { text: string; roomId: string; baseLayoutId: string; furnitureId?: string; channel: 'app' }) => req<AgentResponse>('/agent/request', { method: 'POST', body: JSON.stringify(body) }),
  assessRent: (body: RentAssessBody) => req<{ assessment: RentAssessment; benchmarks: { source: string; value: number; label: string; observedAt: string; sourceUrl: string }[] }>('/rent/assess', { method: 'POST', body: JSON.stringify(body) }),
  housingProfile: (id: string) => req<{ profile: HousingProfile | null }>(`/rooms/${id}/housing-profile`),
  saveHousingProfile: (body: HousingProfile) => req<{ profile: HousingProfile }>(`/rooms/${body.roomId}/housing-profile`, { method: 'PUT', body: JSON.stringify(body) }),
  latestAssessment: (id: string) => req<{ assessment: RentAssessment | null; status?: string }>(`/rooms/${id}/rent-assessment`),
  addresses: (q: string, mode: string) => req<{ candidates: AddressCandidate[]; source: SourceInfo }>(`/housing/addresses?q=${encodeURIComponent(q)}&mode=${mode}`),
  searchComparables: (profile: HousingProfile) => req<{ comparables: RentalComparable[]; source: SourceInfo }>('/housing/comparables/search', { method: 'POST', body: JSON.stringify(profile) }),
  seedTenancy: (roomId: string) => req<{ tenancy: Tenancy; notice: string }>('/payments/test-tenancy', { method: 'POST', body: JSON.stringify({ roomId }) }),
  paymentQuote: (body: QuoteRequest) => req<{ quote: PaymentQuote }>('/payments/quote', { method: 'POST', body: JSON.stringify(body) }),
  paymentCheckout: (quoteId: string) => req<{ payment: PaymentRecord; url: string | null }>('/payments/checkout', { method: 'POST', body: JSON.stringify({ quoteId, confirmed: true }) }),
  payment: (id: string) => req<{ payment: PaymentRecord }>(`/payments/${id}`),
  payments: (roomId: string) => req<{ payments: PaymentRecord[] }>(`/payments?roomId=${roomId}`),
  simulatePayment: (id: string, outcome: string) => req<{ payment: PaymentRecord }>(`/payments/${id}/simulate`, { method: 'POST', body: JSON.stringify({ outcome }) }),
  photos: (roomId: string) => req<{ photos: EvidencePhoto[] }>(`/rooms/${roomId}/evidence`),
  uploadEvidence: async (roomId: string, file: File) => {
    const body = new FormData(); body.append('image', file);
    const response = await fetch(`${base}/rooms/${roomId}/evidence`, { method: 'POST', headers: await sessionHeaders(), body });
    if (!response.ok) throw new Error((await response.json()).detail ?? 'Photo upload failed');
    return response.json() as Promise<{ photo: EvidencePhoto }>;
  },
  photoBlob: async (id: string) => {
    const response = await fetch(`${base}/evidence/${id}`, { headers: await sessionHeaders() });
    if (!response.ok) throw new Error('Photo unavailable');
    return response.blob();
  },
  deletePhoto: (id: string) => req<void>(`/evidence/${id}`, { method: 'DELETE' }),
  manualFurniture: (body: unknown) => req<FurnitureItem>('/furniture/manual', { method: 'POST', body: JSON.stringify(body) }),
  confirmFurniture: (id: string, body: unknown) => req<FurnitureItem>(`/furniture/${id}/details`, { method: 'PATCH', body: JSON.stringify(body) }),
};

export function unwrapLayout(r: LayoutResponse | Layout): Layout { return 'layout' in r ? r.layout : r; }
export function unwrapItem(r: FurnitureItem | { item: FurnitureItem }): FurnitureItem { return 'item' in r ? r.item : r; }
