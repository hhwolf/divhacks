import { createClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined;
export const auth = url && key ? createClient(url, key) : null;

export function demoSession() {
  let value = localStorage.getItem('arp-demo-session');
  if (!value) { value = crypto.randomUUID(); localStorage.setItem('arp-demo-session', value); }
  return value;
}

export async function sessionHeaders(): Promise<Record<string, string>> {
  const session = auth ? (await auth.auth.getSession()).data.session : null;
  return session ? { Authorization: `Bearer ${session.access_token}` } : { 'X-Demo-Session': demoSession() };
}

export function externalUrl(value?: string | null): string | undefined {
  if (!value) return undefined;
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined; } catch { return undefined; }
}
