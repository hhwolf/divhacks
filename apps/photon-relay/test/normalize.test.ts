import { describe, expect, it } from 'vitest';
import { composeReply, normalizeSpectrumMessage } from '../src/normalize.js';

describe('normalizeSpectrumMessage', () => {
  it('normalizes text and sender ids from Spectrum-like messages', async () => {
    const msg = await normalizeSpectrumMessage({
      id: 'm1',
      sender: { id: '+15551234567' },
      content: { type: 'text', text: 'https://facebook.com/marketplace/item/123' },
    });
    expect(msg).toEqual({ messageId: 'm1', sender: '+15551234567', text: 'https://facebook.com/marketplace/item/123', attachments: [] });
  });

  it('normalizes image attachments with lazy bytes', async () => {
    const msg = await normalizeSpectrumMessage({
      guid: 'm2',
      from: '+15557654321',
      text: 'Could this fit?',
      attachments: [{
        mimeType: 'image/jpeg',
        fileName: 'desk.jpg',
        read: async () => new Uint8Array([1, 2, 3]),
      }],
    });
    expect(msg.attachments).toEqual([{ mimeType: 'image/jpeg', fileName: 'desk.jpg', dataBase64: 'AQID' }]);
  });

  it('requires message id and sender', async () => {
    await expect(normalizeSpectrumMessage({ sender: { id: '+1' } })).rejects.toThrow(/missing id/);
    await expect(normalizeSpectrumMessage({ id: 'm1' })).rejects.toThrow(/missing sender/);
  });
});

describe('composeReply', () => {
  it('joins reply and links for a single iMessage send', () => {
    expect(composeReply({ reply: 'Imported.', links: ['roomplanner://layout/abc'] })).toBe('Imported.\nroomplanner://layout/abc');
  });
});
