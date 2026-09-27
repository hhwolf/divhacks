import { createHmac } from 'node:crypto';
import type { BackendResponse, NormalizedPhotonMessage } from './types.js';

export function signedHeaders(raw: string, secret: string, now = Date.now()): Record<string, string> {
  const ts = Math.floor(now / 1000).toString();
  const sig = createHmac('sha256', secret).update(`v0:${ts}:`).update(raw).digest('hex');
  return {
    'content-type': 'application/json',
    'x-arp-relay-timestamp': ts,
    'x-arp-relay-signature': `v0=${sig}`,
  };
}

export async function postNormalizedMessage(apiUrl: string, secret: string, message: NormalizedPhotonMessage): Promise<BackendResponse> {
  const raw = JSON.stringify(message);
  const response = await fetch(`${apiUrl.replace(/\/$/, '')}/webhooks/photon/normalized`, {
    method: 'POST',
    headers: signedHeaders(raw, secret),
    body: raw,
  });
  if (!response.ok) throw new Error(`API rejected Photon message: ${response.status} ${await response.text()}`);
  return response.json() as Promise<BackendResponse>;
}
