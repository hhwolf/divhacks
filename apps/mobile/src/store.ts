import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';

import type { AgentRequestResponse, RoomDraft, Units } from './types';

const STORAGE_KEY = 'arp.settings.v1';

export const DEFAULT_API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';
export const DEFAULT_WEB_URL = process.env.EXPO_PUBLIC_WEB_URL ?? 'http://localhost:5173';

export interface AgentLogEntry {
  id: string;
  at: number;
  text: string;
  roomId: string;
  baseLayoutId: string;
  furnitureId?: string;
  pending: boolean;
  error?: string;
  response?: AgentRequestResponse;
}

interface PersistedSettings { units: Units; apiUrl: string; webUrl: string; onboarded?: boolean }

interface AppState extends PersistedSettings {
  onboarded: boolean;
  setOnboarded: (onboarded: boolean) => void;
  hydrated: boolean;
  agentLog: AgentLogEntry[];
  /** Captured-but-not-created room handed from scan / dimensions to /setup. In-memory only. */
  roomDraft: RoomDraft | null;
  setRoomDraft: (draft: RoomDraft | null) => void;
  hydrate: () => Promise<void>;
  setUnits: (units: Units) => void;
  setUrls: (urls: Partial<Pick<PersistedSettings, 'apiUrl' | 'webUrl'>>) => void;
  resetUrls: () => void;
  pushAgentLog: (entry: AgentLogEntry) => void;
  updateAgentLog: (id: string, patch: Partial<AgentLogEntry>) => void;
}

function stripSlash(u: string): string {
  return u.trim().replace(/\/+$/, '');
}

async function persist(s: PersistedSettings) {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch (e) {
    console.warn('settings persist failed', e);
  }
}

export const useStore = create<AppState>((set, get) => ({
  units: 'imperial',
  apiUrl: DEFAULT_API_URL,
  webUrl: DEFAULT_WEB_URL,
  onboarded: false,
  hydrated: false,
  agentLog: [],
  roomDraft: null,
  setRoomDraft: (roomDraft) => set({ roomDraft }),

  setOnboarded: (onboarded) => {
    set({ onboarded });
    const { units, apiUrl, webUrl } = get();
    void persist({ units, apiUrl, webUrl, onboarded });
  },

  hydrate: async () => {
    try {
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as Partial<PersistedSettings>;
        set({
          units: saved.units === 'metric' ? 'metric' : 'imperial',
          apiUrl: saved.apiUrl ? stripSlash(saved.apiUrl) : DEFAULT_API_URL,
          webUrl: saved.webUrl ? stripSlash(saved.webUrl) : DEFAULT_WEB_URL,
          onboarded: saved.onboarded === true,
        });
      }
    } catch (e) {
      console.warn('settings hydrate failed', e);
    } finally {
      set({ hydrated: true });
    }
  },

  setUnits: (units) => {
    set({ units });
    const { apiUrl, webUrl } = get();
    void persist({ units, apiUrl, webUrl, onboarded: get().onboarded });
  },

  setUrls: (urls) => {
    const next = {
      apiUrl: urls.apiUrl !== undefined ? stripSlash(urls.apiUrl) || DEFAULT_API_URL : get().apiUrl,
      webUrl: urls.webUrl !== undefined ? stripSlash(urls.webUrl) || DEFAULT_WEB_URL : get().webUrl,
    };
    set(next);
    void persist({ units: get().units, onboarded: get().onboarded, ...next });
  },

  resetUrls: () => {
    set({ apiUrl: DEFAULT_API_URL, webUrl: DEFAULT_WEB_URL });
    void persist({ units: get().units, onboarded: get().onboarded, apiUrl: DEFAULT_API_URL, webUrl: DEFAULT_WEB_URL });
  },

  pushAgentLog: (entry) => set((s) => ({ agentLog: [entry, ...s.agentLog] })),
  updateAgentLog: (id, patch) =>
    set((s) => ({ agentLog: s.agentLog.map((e) => (e.id === id ? { ...e, ...patch } : e)) })),
}));
