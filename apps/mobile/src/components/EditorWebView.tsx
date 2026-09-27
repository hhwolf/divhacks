import { MaterialCommunityIcons } from '@expo/vector-icons';
import { File, Paths } from 'expo-file-system';
import { useFocusEffect, useRouter } from 'expo-router';
import * as ScreenOrientation from 'expo-screen-orientation';
import * as Sharing from 'expo-sharing';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Animated, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';

import { EditorMessage, editorRouteUrl, hostInjection, HostMessage, parseEditorMessage } from '../bridge';
import { useStore } from '../store';
import { colors, radius, shadow } from '../theme';
import type { LayoutMetrics } from '../types';
import { useToast } from './Toast';

interface Props {
  /** Editor route to embed, e.g. `/layout/abc` or `/compare/a/b`. `embedded=1&units=` is appended. */
  route: string;
  /** Layout to announce with `host:openLayout` after `editor:ready` (omit for compare view). */
  layoutId?: string;
  /** Known room id (used when the editor asks to navigate to /ask). */
  roomId?: string;
  /** Benchmark C5: after `editor:ready`, drive a synthetic drag for 3 s and report the WebView's fps via editor:log. */
  fpsProbe?: boolean;
}

/**
 * Injected into the page: moves the first unlocked item along a small orbit on every animation frame for 3 s (the same
 * store call the pointer drag uses) and posts `editor:log {message:'fps', data:{fps, frames, ms}}` back to the host.
 */
const FPS_PROBE_JS = `(function(){
  var store = window.__arpStore; if (!store) return;
  var st = store.getState(); var item = (st.items || []).find(function(i){ return !i.locked; }); if (!item) return;
  var id = item.id, cx = item.x, cz = item.z, frames = 0, t0 = performance.now();
  function tick(now){
    frames++; var a = (now - t0) / 500;
    store.getState().moveItem(id, cx + Math.cos(a) * 0.4, cz + Math.sin(a) * 0.4, { free: true, commit: false });
    if (now - t0 < 3000) requestAnimationFrame(tick);
    else {
      var ms = now - t0; store.getState().moveItem(id, cx, cz, { free: true, commit: false });
      window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'editor:log', payload: { message: 'fps', data: { fps: Math.round(frames / (ms / 1000)), frames: frames, ms: Math.round(ms) } } }));
    }
  }
  requestAnimationFrame(tick);
})(); true;`;

/**
 * Full-bleed WebView hosting the web editor, locked to landscape while focused, with the typed bridge,
 * a floating native back button and a transient metrics chip.
 */
export function EditorWebView({ route, layoutId, roomId: roomIdProp, fpsProbe }: Props) {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const { units, apiUrl, webUrl } = useStore();
  const webRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<LayoutMetrics | null>(null);
  const [roomId, setRoomId] = useState<string | undefined>(roomIdProp);
  const [currentLayoutId, setCurrentLayoutId] = useState<string | undefined>(layoutId);
  const chipOpacity = useRef(new Animated.Value(0)).current;
  const chipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const url = editorRouteUrl(webUrl, route, units);

  // Landscape while focused; every other screen is portrait, so lock back explicitly on blur/unmount (a plain
  // unlock leaves the interface in landscape until the device is physically rotated).
  useFocusEffect(
    useCallback(() => {
      ScreenOrientation.lockAsync(ScreenOrientation.OrientationLock.LANDSCAPE).catch(() => {});
      return () => {
        ScreenOrientation.lockAsync(ScreenOrientation.OrientationLock.PORTRAIT_UP).catch(() => {});
      };
    }, []),
  );

  const send = useCallback((msg: HostMessage) => {
    webRef.current?.injectJavaScript(hostInjection(msg));
  }, []);

  const sendHello = useCallback(() => {
    send({ type: 'host:hello', payload: { platform: Platform.OS === 'ios' ? 'ios' : Platform.OS === 'android' ? 'android' : 'web', units, apiUrl } });
  }, [send, units, apiUrl]);

  // Keep the editor's units in sync if the user changes Settings while this screen is mounted.
  const firstUnits = useRef(units);
  useEffect(() => {
    if (firstUnits.current !== units) send({ type: 'host:units', payload: { units } });
  }, [units, send]);

  const showMetrics = useCallback(
    (m: LayoutMetrics) => {
      setMetrics(m);
      if (chipTimer.current) clearTimeout(chipTimer.current);
      Animated.timing(chipOpacity, { toValue: 1, duration: 120, useNativeDriver: true }).start();
      chipTimer.current = setTimeout(() => {
        Animated.timing(chipOpacity, { toValue: 0, duration: 300, useNativeDriver: true }).start();
      }, 2000);
    },
    [chipOpacity],
  );

  const saveAndShareSnapshot = useCallback(
    async (dataUrl: string, name?: string) => {
      try {
        const comma = dataUrl.indexOf(',');
        const base64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
        const safe = (name ?? currentLayoutId ?? 'layout').replace(/[^a-z0-9-_]+/gi, '_');
        const file = new File(Paths.cache, `arp-${safe}-${Date.now()}.png`);
        file.write(base64, { encoding: 'base64' });
        if (await Sharing.isAvailableAsync()) {
          await Sharing.shareAsync(file.uri, { mimeType: 'image/png', UTI: 'public.png', dialogTitle: 'Share room snapshot' });
        } else {
          toast(`Snapshot saved to ${file.uri}`);
        }
      } catch (e) {
        toast(`Snapshot failed: ${(e as Error).message}`, { tone: 'danger' });
      }
    },
    [currentLayoutId, toast],
  );

  const navigate = useCallback(
    (route: string, extra: { roomId?: string; layoutId?: string; replace?: boolean }) => {
      const path = route.split('?')[0];
      const parts = path.split('/').filter(Boolean);
      const rid = extra.roomId ?? roomId;
      const lid = extra.layoutId ?? currentLayoutId;
      const go = extra.replace ? router.replace : router.push;
      if (parts[0] === 'compare' && parts[1] && parts[2]) {
        go(`/compare/${encodeURIComponent(parts[1])}/${encodeURIComponent(parts[2])}`);
      } else if (parts[0] === 'layout' && parts[1]) {
        // The editor announces its own URL on load (replace:true); re-pushing the layout we already show would
        // mount a new WebView that announces itself again — an endless push loop.
        if (parts[1] === (currentLayoutId ?? layoutId)) return;
        go(`/editor/${encodeURIComponent(parts[1])}`);
      } else if (parts[0] === 'ask') {
        router.push({ pathname: '/ask', params: { roomId: rid ?? '', layoutId: lid ?? '' } });
      } else if (parts[0] === 'variants' || parts[0] === 'rooms') {
        const target = parts[1] ?? rid;
        if (target) router.push(`/variants/${encodeURIComponent(target)}`);
        else router.push('/');
      } else if (parts[0] === 'settings') {
        router.push('/settings');
      } else if (parts.length === 0 || parts[0] === 'home') {
        router.dismissTo('/');
      } else {
        toast(`Unknown editor route: ${route}`);
      }
    },
    [router, roomId, currentLayoutId, layoutId, toast],
  );

  const onMessage = useCallback(
    (event: WebViewMessageEvent) => {
      const msg: EditorMessage | null = parseEditorMessage(event.nativeEvent.data);
      if (!msg) return;
      switch (msg.type) {
        case 'editor:ready':
          sendHello();
          if (layoutId) send({ type: 'host:openLayout', payload: { layoutId } });
          setLoading(false);
          if (fpsProbe) setTimeout(() => webRef.current?.injectJavaScript(FPS_PROBE_JS), 2500); // let GLBs settle first
          break;
        case 'editor:layoutChanged':
          if (msg.payload.roomId) setRoomId(msg.payload.roomId);
          if (msg.payload.layoutId) setCurrentLayoutId(msg.payload.layoutId);
          if (msg.payload.metrics) showMetrics(msg.payload.metrics);
          break;
        case 'editor:metrics':
          if (msg.payload.metrics) showMetrics(msg.payload.metrics);
          break;
        case 'editor:snapshot':
          void saveAndShareSnapshot(msg.payload.dataUrl, msg.payload.name ?? msg.payload.layoutId);
          break;
        case 'editor:navigate':
          navigate(msg.payload.route, msg.payload);
          break;
        case 'editor:agentReply':
          toast(msg.payload.reply, { tone: msg.payload.status === 'rejected' ? 'danger' : 'ink', ms: 4000 });
          break;
        case 'editor:selection':
          break;
        case 'editor:log': {
          if (msg.payload.message === 'fps') {
            const fps = (msg.payload.data as { fps?: number } | undefined)?.fps;
            toast(`WebView drag: ${fps ?? '?'} fps`, { tone: 'ink', ms: 6000 });
          }
          const level = msg.payload.level ?? 'info';
          const fn = level === 'error' ? console.error : level === 'warn' ? console.warn : console.log;
          fn(`[editor] ${msg.payload.message}`, msg.payload.data ?? '');
          break;
        }
      }
    },
    [fpsProbe, layoutId, navigate, saveAndShareSnapshot, send, sendHello, showMetrics, toast],
  );

  const top = insets.top + 8;
  // In landscape the Dynamic Island / notch sits on one side; the page has no safe-area CSS, so keep the WebView out of
  // that strip and park the Back button inside it (falls back to the page's top-left corner on notch-less devices).
  const left = insets.left >= 48 ? 8 : insets.left + 8;
  const right = insets.right + 8;

  return (
    <View style={[styles.root, { paddingLeft: insets.left, paddingRight: insets.right }]}>
      <WebView
        ref={webRef}
        source={{ uri: url }}
        style={styles.web}
        originWhitelist={['*']}
        javaScriptEnabled
        domStorageEnabled
        allowsInlineMediaPlayback
        mediaPlaybackRequiresUserAction={false}
        allowsBackForwardNavigationGestures={false}
        bounces={false}
        scrollEnabled={false}
        setSupportMultipleWindows={false}
        onMessage={onMessage}
        onLoadEnd={() => {
          sendHello();
          // If the editor never posts editor:ready (older build), still drop the spinner after a moment.
          setTimeout(() => setLoading(false), 1500);
        }}
        onError={(e) => setLoadError(e.nativeEvent.description || 'Failed to load editor')}
        onHttpError={(e) => setLoadError(`HTTP ${e.nativeEvent.statusCode} from ${webUrl}`)}
        webviewDebuggingEnabled
      />

      {loading && !loadError ? (
        <View style={styles.center} pointerEvents="none">
          <ActivityIndicator color={colors.tile} size="large" />
          <Text style={styles.loadingText}>Loading editor…</Text>
        </View>
      ) : null}

      {loadError ? (
        <View style={styles.center}>
          <Text style={styles.errorTitle}>Can't reach the web editor</Text>
          <Text style={styles.errorBody}>{loadError}</Text>
          <Text style={styles.errorBody}>{url}</Text>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
            <Pressable
              style={styles.pillButton}
              onPress={() => {
                setLoadError(null);
                setLoading(true);
                webRef.current?.reload();
              }}
            >
              <Text style={styles.pillText}>Retry</Text>
            </Pressable>
            <Pressable style={styles.pillButton} onPress={() => router.push('/settings')}>
              <Text style={styles.pillText}>Settings</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      <Pressable
        onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))}
        accessibilityRole="button"
        accessibilityLabel="Back"
        hitSlop={8}
        style={({ pressed }) => [styles.back, { top, left }, pressed && { opacity: 0.7 }]}
      >
        <MaterialCommunityIcons name="chevron-left" size={26} color={colors.tile} />
      </Pressable>

      {metrics ? (
        <Animated.View pointerEvents="none" style={[styles.chip, { top, right, opacity: chipOpacity }]}>
          <MaterialCommunityIcons name="floor-plan" size={14} color={colors.tile} />
          <Text style={styles.chipText}>{Math.round(metrics.openFloor * (metrics.openFloor <= 1 ? 100 : 1))}% open</Text>
          <View style={[styles.dot, { backgroundColor: metrics.conflicts > 0 ? colors.danger : colors.accent }]} />
          <Text style={styles.chipText}>
            {metrics.conflicts} conflict{metrics.conflicts === 1 ? '' : 's'}
          </Text>
        </Animated.View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  // Matches the editor page's own background so the safe-area strips blend in.
  root: { flex: 1, backgroundColor: '#D6D1C9' },
  web: { flex: 1, backgroundColor: '#D6D1C9' },
  center: { position: 'absolute', inset: 0, alignItems: 'center', justifyContent: 'center', padding: 24, backgroundColor: 'rgba(243,244,239,0.92)' },
  loadingText: { color: colors.tile, marginTop: 10, fontWeight: '600' },
  errorTitle: { color: colors.ink, fontSize: 18, fontWeight: '800', marginBottom: 6 },
  errorBody: { color: colors.ink, fontSize: 13, textAlign: 'center', marginTop: 2 },
  pillButton: { backgroundColor: colors.ink, paddingHorizontal: 16, paddingVertical: 10, borderRadius: radius.pill },
  pillText: { color: colors.tile, fontWeight: '700' },
  back: {
    position: 'absolute',
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.pill,
    backgroundColor: 'rgba(37,52,32,0.88)',
    ...shadow.soft,
  },
  chip: {
    position: 'absolute',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    height: 32,
    paddingHorizontal: 12,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(37,52,32,0.88)',
    ...shadow.soft,
  },
  chipText: { color: colors.tile, fontWeight: '700', fontSize: 12 },
  dot: { width: 8, height: 8, borderRadius: 4 },
});
