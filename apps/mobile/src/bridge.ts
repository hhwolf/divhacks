// Typed postMessage bridge between the Expo host and the web editor rendered in react-native-webview.
//
// Wire format (both directions): JSON string of { type, id?, payload? }.
//   host  -> editor : webViewRef.injectJavaScript(`window.__ARP_HOST__ && window.__ARP_HOST__.receive(<json>); true;`)
//   editor -> host  : window.ReactNativeWebView.postMessage(JSON.stringify(msg))  (arrives in WebView onMessage)
//
// The editor must expose `window.__ARP_HOST__ = { receive(msg) {...} }` before it sends `editor:ready`.
// The host sends `host:hello` once when the page finishes loading and again on `editor:ready`, then
// `host:openLayout` right after `editor:ready`.

import type { LayoutMetrics, Units } from './types';

export type BridgeType =
  | 'host:hello' | 'editor:ready' | 'host:openLayout' | 'editor:layoutChanged' | 'editor:selection'
  | 'editor:snapshot' | 'host:units' | 'editor:metrics' | 'host:request' | 'editor:agentReply' | 'editor:navigate' | 'editor:log';

export interface BridgeMessage<T = unknown> { type: BridgeType; id?: string; payload?: T }

// ---- host -> editor ----
export interface HostHello { platform: 'ios' | 'android' | 'web'; units: Units; apiUrl: string; appVersion?: string }
export interface HostOpenLayout { layoutId: string }
export interface HostUnits { units: Units }
export interface HostRequest { text: string; furnitureId?: string }

export type HostMessage =
  | { type: 'host:hello'; id?: string; payload: HostHello }
  | { type: 'host:openLayout'; id?: string; payload: HostOpenLayout }
  | { type: 'host:units'; id?: string; payload: HostUnits }
  | { type: 'host:request'; id?: string; payload: HostRequest };

// ---- editor -> host ----
export interface EditorReady { layoutId?: string; version?: string }
export interface EditorLayoutChanged { layoutId: string; metrics: LayoutMetrics; roomId?: string }
export interface EditorSelection { itemId: string | null; furnitureId?: string | null; name?: string | null }
export interface EditorSnapshot { dataUrl: string; layoutId?: string; name?: string }
export interface EditorMetrics { layoutId?: string; metrics: LayoutMetrics }
export interface EditorAgentReply { reply: string; status?: 'ok' | 'clarify' | 'rejected'; layoutId?: string }
/** `route` is an editor path such as `/compare/{a}/{b}`, `/layout/{id}`, `/ask`, `/variants`, `/settings`. */
export interface EditorNavigate { route: string; roomId?: string; layoutId?: string }
export interface EditorLog { level?: 'debug' | 'info' | 'warn' | 'error'; message: string; data?: unknown }

export type EditorMessage =
  | { type: 'editor:ready'; id?: string; payload?: EditorReady }
  | { type: 'editor:layoutChanged'; id?: string; payload: EditorLayoutChanged }
  | { type: 'editor:selection'; id?: string; payload: EditorSelection }
  | { type: 'editor:snapshot'; id?: string; payload: EditorSnapshot }
  | { type: 'editor:metrics'; id?: string; payload: EditorMetrics }
  | { type: 'editor:agentReply'; id?: string; payload: EditorAgentReply }
  | { type: 'editor:navigate'; id?: string; payload: EditorNavigate }
  | { type: 'editor:log'; id?: string; payload: EditorLog };

const EDITOR_TYPES = new Set<EditorMessage['type']>([
  'editor:ready', 'editor:layoutChanged', 'editor:selection', 'editor:snapshot',
  'editor:metrics', 'editor:agentReply', 'editor:navigate', 'editor:log',
]);

/** JS snippet for `webViewRef.current.injectJavaScript(...)`. Ends with `true;` as react-native-webview requires. */
export function hostInjection(msg: HostMessage): string {
  // JSON.stringify output is a valid JS expression; escape U+2028/2029 which are legal in JSON but not in JS strings.
  const literal = JSON.stringify(msg).replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
  return `window.__ARP_HOST__ && window.__ARP_HOST__.receive(${literal}); true;`;
}

/** Parses a WebView `onMessage` payload; returns null for anything that is not a well-formed editor message. */
export function parseEditorMessage(raw: string): EditorMessage | null {
  try {
    const obj = JSON.parse(raw) as { type?: unknown };
    if (!obj || typeof obj !== 'object' || typeof obj.type !== 'string') return null;
    if (!EDITOR_TYPES.has(obj.type as EditorMessage['type'])) return null;
    return obj as EditorMessage;
  } catch {
    return null;
  }
}

/** Builds the embedded editor URL for a layout. */
export function layoutUrl(webUrl: string, layoutId: string, units: Units): string {
  return `${webUrl}/layout/${encodeURIComponent(layoutId)}?embedded=1&units=${units}`;
}

/** Builds any embedded editor route (e.g. `/compare/a/b`). */
export function editorRouteUrl(webUrl: string, route: string, units: Units): string {
  const path = route.startsWith('/') ? route : `/${route}`;
  const sep = path.includes('?') ? '&' : '?';
  return `${webUrl}${path}${sep}embedded=1&units=${units}`;
}
