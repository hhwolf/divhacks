// Web build of the editor host (Expo web preview): react-native-webview has no web implementation, so the editor is
// embedded in an <iframe>. The native bridge (injectJavaScript / onMessage) isn't available here; the editor runs
// standalone against the same API, which is enough to preview and use it from a browser.

import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { editorRouteUrl } from '../bridge';
import { useStore } from '../store';
import { colors, radius, shadow } from '../theme';

interface Props { route: string; layoutId?: string; roomId?: string; fpsProbe?: boolean }

export function EditorWebView({ route }: Props) {
  const router = useRouter();
  const { units, webUrl, apiUrl } = useStore();
  const url = `${editorRouteUrl(webUrl, route, units)}&api=${encodeURIComponent(apiUrl)}`;
  // Slim left rail for Back (like the notch strip on device) so it never covers the editor's own top-left cluster.
  return (
    <View style={styles.root}>
      <View style={styles.rail}>
        <Pressable onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))} accessibilityRole="button" accessibilityLabel="Back" style={styles.back}>
          <MaterialCommunityIcons name="chevron-left" size={24} color={colors.white} />
        </Pressable>
      </View>
      <View style={{ flex: 1 }}>
        {React.createElement('iframe', { src: url, title: 'Room editor', style: { border: 0, width: '100%', height: '100%', display: 'block' } })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, flexDirection: 'row', backgroundColor: '#D6D1C9' },
  rail: { width: 52, alignItems: 'center', paddingTop: 12, backgroundColor: '#D6D1C9' },
  back: { width: 38, height: 38, alignItems: 'center', justifyContent: 'center', borderRadius: radius.pill, backgroundColor: colors.forest, ...shadow.soft },
});
