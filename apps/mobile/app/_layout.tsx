import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React, { useEffect } from 'react';
import { ActivityIndicator, View } from 'react-native';

import { SafeAreaInsetsContext } from 'react-native-safe-area-context';

import { ToastProvider } from '../src/components/Toast';
import { installCrashGuard } from '../src/crashGuard';
import { useStore } from '../src/store';
import { colors } from '../src/theme';
import { webInsetsOverride } from '../src/webInsets';

const insetsOverride = webInsetsOverride();

installCrashGuard();

export default function RootLayout() {
  const hydrated = useStore((s) => s.hydrated);
  const hydrate = useStore((s) => s.hydrate);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  if (!hydrated) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator color={colors.ink} />
      </View>
    );
  }

  const tree = (
    <ToastProvider>
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.bg },
          headerShadowVisible: false,
          headerTintColor: colors.ink,
          headerTitleStyle: { fontWeight: '700', color: colors.ink },
          headerBackButtonDisplayMode: 'minimal',
          contentStyle: { backgroundColor: colors.bg },
        }}
      >
        <Stack.Screen name="index" options={{ headerShown: false }} />
        <Stack.Screen name="welcome" options={{ headerShown: false, gestureEnabled: false, animation: 'fade' }} />
        <Stack.Screen name="scan" options={{ title: 'Scan room' }} />
        <Stack.Screen name="setup" options={{ title: 'Set up room' }} />
        <Stack.Screen name="editor/[layoutId]" options={{ headerShown: false, animation: 'fade' }} />
        <Stack.Screen name="compare/[a]/[b]" options={{ headerShown: false, animation: 'fade' }} />
        <Stack.Screen name="layout/[id]" options={{ headerShown: false }} />
        <Stack.Screen name="ask" options={{ title: 'Ask the planner' }} />
        <Stack.Screen name="variants/[roomId]" options={{ title: 'Variants' }} />
        <Stack.Screen name="settings" options={{ title: 'Settings', presentation: 'modal' }} />
      </Stack>
    </ToastProvider>
  );
  // Phone-frame preview on web: simulate the device's safe areas (see src/webInsets.ts).
  return insetsOverride ? <SafeAreaInsetsContext.Provider value={insetsOverride}>{tree}</SafeAreaInsetsContext.Provider> : tree;
}
