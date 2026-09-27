import { createHmac } from 'node:crypto';
import { describe, expect, it, vi } from 'vitest';
import { postNormalizedMessage, signedHeaders } from '../src/backend.js';

describe('signedHeaders', () => {
  it('signs the exact JSON body with the relay secret', () => {
    const raw = '{"messageId":"m1"}';
    const headers = signedHeaders(raw, 'secret', 1_700_000_000_000);
    const expected = createHmac('sha256', 'secret').update('v0:1700000000:').update(raw).digest('hex');
    expect(headers['x-arp-relay-timestamp']).toBe('1700000000');
    expect(headers['x-arp-relay-signature']).toBe(`v0=${expected}`);
  });
});

describe('postNormalizedMessage', () => {
  it('posts normalized payloads to FastAPI', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(JSON.stringify({ ok: true, reply: 'Done' }), { status: 200 }));
    const out = await postNormalizedMessage('https://api.test/', 'secret', { messageId: 'm1', sender: '+1', text: 'hi', attachments: [] });
    expect(out.reply).toBe('Done');
    expect(fetchMock.mock.calls[0]?.[0]).toBe('https://api.test/webhooks/photon/normalized');
    fetchMock.mockRestore();
  });

  it('throws when FastAPI fails so the relay can send a safe fallback', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response('nope', { status: 500 }));
    await expect(postNormalizedMessage('https://api.test', 'secret', { messageId: 'm1', sender: '+1', text: 'hi', attachments: [] })).rejects.toThrow(/500/);
    fetchMock.mockRestore();
  });
});
