import { useStore } from './store';
import type {
  AgentRequestResponse,
  CreateRoomResponse,
  Dimensions,
  FurnitureItem,
  HealthResponse,
  Layout,
  Room,
  RoomDetailResponse,
  RoomListEntry,
  RoomPlanExport,
} from './types';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function baseUrl(): string {
  return useStore.getState().apiUrl;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = `${baseUrl()}${path}`;
  const headers: Record<string, string> = { Accept: 'application/json', ...(init.headers as Record<string, string> | undefined) };
  const isForm = typeof FormData !== 'undefined' && init.body instanceof FormData;
  if (init.body && !isForm && !headers['Content-Type']) headers['Content-Type'] = 'application/json';

  let res: Response;
  try {
    res = await fetch(url, { ...init, headers });
  } catch (e) {
    throw new ApiError(0, `Cannot reach API at ${baseUrl()} (${(e as Error).message}). Check Settings.`);
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    const detail =
      typeof data === 'object' && data !== null && 'detail' in data
        ? typeof (data as { detail: unknown }).detail === 'string'
          ? (data as { detail: string }).detail
          : JSON.stringify((data as { detail: unknown }).detail)
        : typeof data === 'string' && data
          ? data
          : res.statusText;
    throw new ApiError(res.status, `${res.status}: ${detail}`);
  }
  return data as T;
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  health: () => request<HealthResponse>('/health'),

  listRooms: async (): Promise<RoomListEntry[]> => {
    const data = await request<RoomListEntry[] | { rooms: RoomListEntry[] }>('/rooms');
    return Array.isArray(data) ? data : data.rooms ?? [];
  },
  getRoom: (id: string) => request<RoomDetailResponse>(`/rooms/${encodeURIComponent(id)}`),

  createSampleRoom: (sample = 'nyc-bedroom') =>
    request<CreateRoomResponse>('/rooms', { method: 'POST', body: json({ sample }) }),
  createManualRoom: (dimensions: Dimensions, name = 'My room') =>
    request<CreateRoomResponse>('/rooms', {
      method: 'POST',
      body: json({ dimensions, doors: [], windows: [], name }),
    }),
  createScannedRoom: (scan: RoomPlanExport, name = 'Scanned room') =>
    request<CreateRoomResponse>('/rooms', {
      method: 'POST',
      body: json({ skeleton: scan.skeleton, objects: scan.objects, name }),
    }),
  /** Accepts either our {skeleton, objects} export or a raw RoomPlan JSON export the API knows how to parse. */
  createRoomFromJson: (payload: Record<string, unknown>, name = 'Scanned room') =>
    request<CreateRoomResponse>('/rooms', { method: 'POST', body: json({ name, ...payload }) }),

  /** GET /layouts/{id} returns `{layout, furniture, validation}`; unwrap to the bare Layout. */
  getLayout: async (id: string): Promise<Layout> => {
    const data = await request<Layout | { layout: Layout }>(`/layouts/${encodeURIComponent(id)}`);
    return 'layout' in data ? data.layout : data;
  },
  forkLayout: (id: string, name: string) =>
    request<Layout>(`/layouts/${encodeURIComponent(id)}/fork`, { method: 'POST', body: json({ name }) }),
  updateLayout: (layout: Layout, patch: Partial<Pick<Layout, 'name' | 'items' | 'zones'>>) =>
    request<Layout>(`/layouts/${encodeURIComponent(layout.id)}`, {
      method: 'PUT',
      body: json({
        name: patch.name ?? layout.name,
        items: patch.items ?? layout.items,
        zones: patch.zones ?? layout.zones,
        source: 'editor',
      }),
    }),
  deleteLayout: (id: string) => request<unknown>(`/layouts/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  listFurniture: () => request<FurnitureItem[]>('/furniture'),
  furnitureFromPhoto: async (file: { uri: string; name: string; type: string }): Promise<FurnitureItem> => {
    const form = new FormData();
    // React Native's FormData accepts {uri,name,type} for file parts.
    form.append('image', file as unknown as Blob);
    const data = await request<FurnitureItem | { furniture: FurnitureItem }>('/furniture/from-photo', {
      method: 'POST',
      body: form,
    });
    return 'furniture' in data ? data.furniture : data;
  },

  agentRequest: (body: { text: string; roomId: string; baseLayoutId: string; furnitureId?: string }) =>
    request<AgentRequestResponse>('/agent/request', {
      method: 'POST',
      body: json({ ...body, channel: 'app' }),
    }),
};

export type { Room };
