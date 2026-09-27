import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { Spectrum } from 'spectrum-ts';
import { imessage } from 'spectrum-ts/providers/imessage';
import { spectrum } from '@spectrum-ts/hono';
import { composeReply, normalizeSpectrumMessage } from './normalize.js';
import { postNormalizedMessage } from './backend.js';

const env = {
  projectId: process.env.SPECTRUM_PROJECT_ID ?? '',
  projectSecret: process.env.SPECTRUM_PROJECT_SECRET ?? process.env.PHOTON_API_KEY ?? '',
  webhookSecret: process.env.SPECTRUM_WEBHOOK_SECRET ?? process.env.PHOTON_WEBHOOK_SECRET ?? '',
  apiUrl: process.env.PUBLIC_API_URL ?? 'http://localhost:8000',
  relaySecret: process.env.PHOTON_RELAY_SECRET ?? '',
  port: Number(process.env.PORT ?? 8787),
};

for (const [key, value] of Object.entries(env)) {
  if (key !== 'port' && !value) throw new Error(`${key} is required`);
}

const photon = await Spectrum({
  projectId: env.projectId,
  projectSecret: env.projectSecret,
  providers: [imessage.config()],
  webhookSecret: env.webhookSecret,
});

const app = new Hono();

app.get('/health', (c) => c.json({ ok: true }));

app.route(
  '/spectrum/webhook',
  spectrum({
    app: photon,
    onMessage: async (space: { send: (text: string) => Promise<unknown> }, message: unknown) => {
      try {
        const normalized = await normalizeSpectrumMessage(message);
        const backend = await postNormalizedMessage(env.apiUrl, env.relaySecret, normalized);
        await space.send(composeReply(backend));
      } catch (error) {
        console.error('Photon relay failed', error);
        await space.send('I had trouble importing that item. Please try a clear Marketplace screenshot or open the app to enter dimensions manually.');
      }
    },
  }),
);

serve({ fetch: app.fetch, port: env.port });
console.log(`Photon relay listening on :${env.port}`);
