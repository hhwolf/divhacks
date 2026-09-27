import { createClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined;
export const auth = url && key ? createClient(url, key) : null;

export function randomId() { return Array.from(crypto.getRandomValues(new Uint8Array(24)), (b) => b.toString(16).padStart(2, '0')).join(''); }

export function demoSession() {
  let value = localStorage.getItem('arp-demo-session');
  if (!value) { value = randomId(); localStorage.setItem('arp-demo-session', value); }
  return value;
}

const nativeSession = (window as unknown as { __ARP_NATIVE_SESSION?: { access_token: string; refresh_token: string } | null }).__ARP_NATIVE_SESSION;
const nativeReady = nativeSession !== undefined && auth ? (nativeSession ? auth.auth.setSession(nativeSession).then(({ error }) => { if (error) throw error; }) : auth.auth.signOut()) : Promise.resolve();

export async function sessionHeaders(): Promise<Record<string, string>> {
  await nativeReady;
  if (nativeSession && !auth) throw new Error('Configure matching web and native Supabase projects to open private scans.');
  const session = auth ? (await auth.auth.getSession()).data.session : null;
  return session ? { Authorization: `Bearer ${session.access_token}` } : { 'X-Demo-Session': demoSession() };
}

export function externalUrl(value?: string | null): string | undefined {
  if (!value) return undefined;
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined; } catch { return undefined; }
}
