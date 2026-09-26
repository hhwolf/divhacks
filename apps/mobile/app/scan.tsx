import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useCallback, useMemo, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { EMPTY_EXPORT, getRoomPlanModule, isRoomPlanAvailable, isSupported, RoomPlanView, type CaptureStatus } from '../modules/roomplan';
import { api } from '../src/api';
import { DimensionsSheet } from '../src/components/DimensionsSheet';
import { useToast } from '../src/components/Toast';
import { Button, Chip, Screen, Tile } from '../src/components/ui';
import { useStore } from '../src/store';
import { colors, radius, spacing, type } from '../src/theme';
import type { Dimensions, RoomPlanExport } from '../src/types';

export default function Scan() {
  const supported = useMemo(() => isSupported(), []);
  return supported ? <LiveScan /> : <Fallback />;
}

// ---------------------------------------------------------------------------------------------
// Live RoomPlan capture (dev client on a LiDAR iPhone only).
// ---------------------------------------------------------------------------------------------
function LiveScan() {
  const router = useRouter();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [status, setStatus] = useState<CaptureStatus>('idle');
  const [busy, setBusy] = useState(false);
  const mod = getRoomPlanModule();

  const start = async () => {
    try {
      await mod?.startCapture();
      setStatus('scanning');
    } catch (e) {
      toast(`Could not start capture: ${(e as Error).message}`, { tone: 'danger' });
    }
  };

  const stopAndSave = async () => {
    if (!mod) return;
    setBusy(true);
    try {
      await mod.stopCapture();
      setStatus('processing');
      const scan: RoomPlanExport = (await mod.exportSkeleton()) ?? EMPTY_EXPORT;
      if (!scan.skeleton?.walls?.length) {
        setStatus('idle');
        toast('The scan did not produce any walls yet. Try walking the room slowly.', { tone: 'danger', ms: 4000 });
        return;
      }
      const res = await api.createScannedRoom(scan, 'Scanned room');
      setStatus('done');
      router.replace(`/editor/${encodeURIComponent(res.currentLayout.id)}`);
    } catch (e) {
      setStatus('error');
      toast((e as Error).message, { tone: 'danger', ms: 4500 });
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: '#000' }}>
      <RoomPlanView style={{ flex: 1 }} onCaptureStatus={(e) => setStatus(e.nativeEvent.status)} />
      <View style={[styles.scanBar, { paddingBottom: insets.bottom + spacing.md }]}>
        <Chip
          icon={status === 'scanning' ? 'record-circle' : 'cube-scan'}
          label={status === 'idle' ? 'Ready' : status === 'scanning' ? 'Scanning… walk the room slowly' : status === 'processing' ? 'Processing' : status}
          tone={status === 'scanning' ? 'danger' : 'tile'}
        />
        <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
          <Button label="Start" icon="play" onPress={start} disabled={status === 'scanning' || busy} style={{ flex: 1 }} variant="secondary" />
          <Button label="Stop & save" icon="stop" onPress={stopAndSave} disabled={status !== 'scanning'} busy={busy} style={{ flex: 1 }} />
        </View>
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------------------------
// Fallback (Expo Go, Simulator, non-LiDAR device, Android).
// ---------------------------------------------------------------------------------------------
function Fallback() {
  const router = useRouter();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const units = useStore((s) => s.units);
  const [busy, setBusy] = useState<'sample' | 'manual' | 'paste' | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasted, setPasted] = useState('');

  const reason = isRoomPlanAvailable()
    ? 'This device has no LiDAR sensor, so RoomPlan cannot run here.'
    : 'You are running in Expo Go or the Simulator, where the RoomPlan native module is not linked.';

  const openEditor = useCallback(
    (layoutId: string) => router.replace(`/editor/${encodeURIComponent(layoutId)}`),
    [router],
  );

  const loadSample = async () => {
    setBusy('sample');
    try {
      const res = await api.createSampleRoom('nyc-bedroom');
      openEditor(res.currentLayout.id);
    } catch (e) {
      toast((e as Error).message, { tone: 'danger', ms: 4500 });
    } finally {
      setBusy(null);
    }
  };

  const createManual = async (dims: Dimensions, name: string) => {
    setBusy('manual');
    try {
      const res = await api.createManualRoom(dims, name);
      setSheetOpen(false);
      openEditor(res.currentLayout.id);
    } catch (e) {
      toast((e as Error).message, { tone: 'danger', ms: 4500 });
    } finally {
      setBusy(null);
    }
  };

  const submitPasted = async () => {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(pasted) as Record<string, unknown>;
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('not an object');
    } catch {
      toast('That is not valid JSON. Paste a RoomPlan export or our {skeleton, objects} JSON.', { tone: 'danger', ms: 4000 });
      return;
    }
    setBusy('paste');
    try {
      const name = typeof parsed.name === 'string' ? parsed.name : 'Scanned room';
      const res = await api.createRoomFromJson(parsed, name);
      openEditor(res.currentLayout.id);
    } catch (e) {
      toast((e as Error).message, { tone: 'danger', ms: 4500 });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Screen>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + spacing.xl }]} keyboardShouldPersistTaps="handled">
          <Tile style={{ alignItems: 'center', gap: spacing.sm }}>
            <View style={styles.heroIcon}>
              <MaterialCommunityIcons name="cube-scan" size={40} color={colors.tile} />
            </View>
            <Text style={[type.h2, { textAlign: 'center' }]}>RoomPlan needs a LiDAR iPhone and the dev-client build</Text>
            <Text style={[type.body, { textAlign: 'center', color: colors.inkSoft }]}>{reason}</Text>
            <Text style={[type.small, { textAlign: 'center' }]}>
              Run <Text style={styles.mono}>npx expo run:ios --device</Text> on an iPhone Pro to scan for real. Meanwhile, pick another way in:
            </Text>
          </Tile>

          <View style={{ gap: spacing.sm, marginTop: spacing.lg }}>
            <Button label="Load sample room" icon="bed-king-outline" onPress={loadSample} busy={busy === 'sample'} />
            <Button label="Enter dimensions" icon="ruler-square" variant="secondary" onPress={() => setSheetOpen(true)} />
            <Button
              label={pasteOpen ? 'Hide JSON box' : 'Paste RoomPlan JSON'}
              icon="code-json"
              variant="secondary"
              onPress={() => setPasteOpen((v) => !v)}
            />
          </View>

          {pasteOpen ? (
            <Tile style={{ marginTop: spacing.lg }}>
              <Text style={[type.small, { marginBottom: spacing.sm }]}>
                Paste a RoomPlan export (walls / doors / windows / objects) or our skeleton JSON. It is sent to POST /rooms unchanged.
              </Text>
              <TextInput
                multiline
                value={pasted}
                onChangeText={setPasted}
                placeholder='{"skeleton":{"walls":[...],"doors":[],"windows":[],"floorPolygon":[...],"dimensions":{"l":3.4,"w":3,"h":2.7}},"objects":[]}'
                placeholderTextColor="#A08B7C"
                autoCapitalize="none"
                autoCorrect={false}
                style={styles.textarea}
              />
              <Button label="Create room from JSON" icon="upload" onPress={submitPasted} busy={busy === 'paste'} disabled={!pasted.trim()} style={{ marginTop: spacing.sm }} />
            </Tile>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>

      <DimensionsSheet visible={sheetOpen} units={units} busy={busy === 'manual'} onClose={() => setSheetOpen(false)} onSubmit={createManual} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  heroIcon: { width: 72, height: 72, borderRadius: radius.lg, backgroundColor: colors.ink, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.xs },
  mono: { fontFamily: Platform.select({ ios: 'Menlo', default: 'monospace' }), color: colors.ink },
  textarea: {
    minHeight: 160,
    backgroundColor: colors.white,
    borderRadius: radius.sm,
    padding: spacing.md,
    fontSize: 13,
    color: colors.ink,
    fontFamily: Platform.select({ ios: 'Menlo', default: 'monospace' }),
    textAlignVertical: 'top',
  },
  scanBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    padding: spacing.lg,
    backgroundColor: 'rgba(74,51,39,0.85)',
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
  },
});
