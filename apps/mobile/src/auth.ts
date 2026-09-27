import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';
import { AppState } from 'react-native';
import { nativeDemoSession } from './session';

const url = process.env.EXPO_PUBLIC_SUPABASE_URL;
const key = process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
export const nativeAuth = url && key ? createClient(url, key, { auth: { storage: AsyncStorage, autoRefreshToken: true, persistSession: true, detectSessionInUrl: false } }) : null;
AppState.addEventListener('change', (state) => { if (state === 'active') nativeAuth?.auth.startAutoRefresh(); else nativeAuth?.auth.stopAutoRefresh(); });

export async function nativeHeaders(): Promise<Record<string, string>> {
  const session = nativeAuth ? (await nativeAuth.auth.getSession()).data.session : null;
  return session ? { Authorization: `Bearer ${session.access_token}` } : { 'X-Demo-Session': await nativeDemoSession() };
}

export async function editorSessionScript(webUrl: string, apiUrl: string): Promise<string> {
  const demo = await nativeDemoSession();
  const session = nativeAuth ? (await nativeAuth.auth.getSession()).data.session : null;
  const tokens = session ? { access_token: session.access_token, refresh_token: session.refresh_token } : null;
  return `if (location.origin === ${JSON.stringify(new URL(webUrl).origin)}) { localStorage.setItem('arp-demo-session', ${JSON.stringify(demo)}); window.__ARP_NATIVE_API_URL = ${JSON.stringify(apiUrl)}; window.__ARP_NATIVE_SESSION = ${JSON.stringify(tokens)}; } true;`;
}
