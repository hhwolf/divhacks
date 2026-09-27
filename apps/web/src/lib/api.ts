import type { FurnitureItem, HousingProfile, Layout, PaymentPurpose, PaymentQuote, RentAssessment, Room, ValidationResult } from '@arp/contracts';

let base = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';
export function setApiBase(url: string) { base = url.replace(/\/$/, ''); }
export function apiBase() { return base; }

/** An HTTP error with its status, so callers can react to 403 (read-only) and 409 (stale version). */
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, { headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) }, ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j); } catch { /* ignore */ }
    throw new ApiError(res.status, `${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export interface LayoutResponse { layout: Layout; furniture: Record<string, FurnitureItem>; validation?: ValidationResult; room?: Room }
export interface RoomResponse { room: Room; layouts: Layout[]; currentLayout?: Layout }
export interface AgentOption { variantName: string; layoutId: string | null; explanation: string; tradeoff: string; moved: string[]; validation: { ok: boolean; warnings: number; open_floor_pct: number } }
export interface AgentResponse { plan: unknown; layout: Layout | null; reply: string; status: string; links?: string[]; requestId?: string; options?: AgentOption[]; recommended?: string | null }
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
  saveLayout: (id: string, body: Partial<Layout> & { source: 'editor'; version?: number }) => req<LayoutResponse>(`/layouts/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  fork: (id: string, name?: string) => req<LayoutResponse | Layout>(`/layouts/${id}/fork`, { method: 'POST', body: JSON.stringify({ name }) }),
  deleteLayout: (id: string) => req<unknown>(`/layouts/${id}`, { method: 'DELETE' }),
  compare: (a: string, b: string) => req<CompareResponse>(`/layouts/${a}/compare/${b}`),
  furniture: () => req<{ items: FurnitureItem[] } | FurnitureItem[]>('/furniture'),
  fromLink: (url: string) => req<FurnitureItem | { item: FurnitureItem }>('/furniture/from-link', { method: 'POST', body: JSON.stringify({ url }) }),
  fromPhoto: async (file: File) => {
    const fd = new FormData(); fd.append('image', file);
    const res = await fetch(`${base}/furniture/from-photo`, { method: 'POST', body: fd });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json() as Promise<FurnitureItem | { item: FurnitureItem }>;
  },
  agent: (body: { text: string; roomId: string; baseLayoutId: string; furnitureId?: string; channel: 'app' }) => req<AgentResponse>('/agent/request', { method: 'POST', body: JSON.stringify(body) }),
  assessRent: (body: RentAssessBody) => req<{ assessment: RentAssessment }>('/rent/assess', { method: 'POST', body: JSON.stringify(body) }),
  paymentQuote: (body: { purpose: PaymentPurpose; amount: number; rentAmount?: number | null; roomId?: string; assessmentId?: string }) => req<{ quote: PaymentQuote }>('/payments/quote', { method: 'POST', body: JSON.stringify(body) }),
  paymentCheckout: (body: { purpose: PaymentPurpose; amount: number; rentAmount?: number | null; roomId?: string; assessmentId?: string }) => req<{ quote: PaymentQuote; url: string | null }>('/payments/checkout', { method: 'POST', body: JSON.stringify(body) }),
};

export function unwrapLayout(r: LayoutResponse | Layout): Layout { return 'layout' in r ? r.layout : r; }
export function unwrapItem(r: FurnitureItem | { item: FurnitureItem }): FurnitureItem { return 'item' in r ? r.item : r; }
