import type { BridgeMessage, BridgeType } from '@arp/contracts';

type Handler = (msg: BridgeMessage) => void;
const handlers = new Set<Handler>();
declare global {
  interface Window { ReactNativeWebView?: { postMessage(s: string): void }; __ARP_HOST__?: { receive(msg: BridgeMessage): void } }
}

/** True when running inside the Expo WebView (or ?embedded=1 for testing). */
export function isEmbedded(): boolean {
  return Boolean(window.ReactNativeWebView) || new URLSearchParams(location.search).get('embedded') === '1';
}
export function postToHost<T>(type: BridgeType, payload?: T, id?: string): void {
  const msg: BridgeMessage<T> = { type, payload, id };
  window.ReactNativeWebView?.postMessage(JSON.stringify(msg));
  // Expo web build: the host is the parent page of an iframe. Only post to the page that embedded us.
  const parentOrigin = !window.ReactNativeWebView && window.parent !== window && document.referrer ? new URL(document.referrer).origin : null;
  if (parentOrigin) window.parent.postMessage(JSON.stringify(msg), parentOrigin);
  else if (!window.ReactNativeWebView && isEmbedded()) console.debug('[bridge→host]', msg);
}
export function onHostMessage(h: Handler): () => void { handlers.add(h); return () => handlers.delete(h); }
window.__ARP_HOST__ = { receive(msg) { for (const h of handlers) h(msg); } };
