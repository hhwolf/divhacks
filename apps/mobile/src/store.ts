import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';

import type { AgentRequestResponse, Dimensions, RoomPlanExport, Units } from './types';

/** A room waiting for the setup flow (app/setup.tsx): a finished scan, or typed dimensions. Too large for route params. */
export type PendingSetup = { kind: 'scan'; scan: RoomPlanExport; name?: string } | { kind: 'manual'; dims: Dimensions; name: string };

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
  hydrated: boolean;
  agentLog: AgentLogEntry[];
  pendingSetup: PendingSetup | null;
  setPendingSetup: (p: PendingSetup | null) => void;
  /** First-launch welcome flow (app/welcome.tsx) has been seen. */
  setOnboarded: (v: boolean) => void;
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
  hydrated: false,
  agentLog: [],
  onboarded: false,
  pendingSetup: null,
  setPendingSetup: (pendingSetup) => set({ pendingSetup }),
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
