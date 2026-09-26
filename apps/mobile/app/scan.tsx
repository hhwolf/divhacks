import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import React, { useCallback, useMemo, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  type CaptureProgress,
  type CaptureStatus,
  EMPTY_EXPORT,
  getRoomPlanModule,
  isRoomPlanAvailable,
  isSupported,
  RoomPlanView,
} from '../modules/roomplan';
import { api } from '../src/api';
import { DimensionsSheet } from '../src/components/DimensionsSheet';
import { useToast } from '../src/components/Toast';
import { Button, Chip, Screen, Tile } from '../src/components/ui';
import { useStore } from '../src/store';
import { colors, radius, spacing, type } from '../src/theme';
import type { Dimensions, RoomDraft, RoomPlanExport } from '../src/types';
import { useKeepAwake } from 'expo-keep-awake';
import { Linking } from 'react-native';
import { formatArea, formatDims } from '../src/units';

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
  const units = useStore((s) => s.units);
  const setRoomDraft = useStore((s) => s.setRoomDraft);
  const [progress, setProgress] = useState<CaptureProgress>({ status: 'idle' });
  const [scan, setScan] = useState<RoomPlanExport | null>(null);
  const [busy, setBusy] = useState<'stop' | null>(null);
  const mod = getRoomPlanModule();
  const status: CaptureStatus = progress.status;
  const [cameraDenied, setCameraDenied] = useState(false);
  useKeepAwake(); // a room scan takes a minute or two; never let the screen sleep mid-capture

  const onCaptureStatus = useCallback((e: { nativeEvent: CaptureProgress }) => {
    // Keep the last known counts when an instruction-only event arrives.
    setProgress((prev) => ({ ...prev, ...e.nativeEvent, message: e.nativeEvent.message ?? (e.nativeEvent.status === prev.status ? prev.message : undefined) }));
  }, []);

  const start = async () => {
    try {
      setScan(null);
      setCameraDenied(false);
      await mod?.startCapture();
      setProgress({ status: 'scanning', walls: 0, doors: 0, windows: 0, objects: 0 });
    } catch (e) {
      const err = e as Error & { code?: string };
      const denied = err.code === 'CameraPermissionDenied' || /camera access/i.test(err.message);
      setCameraDenied(denied);
      setProgress({ status: 'error', message: denied ? 'Camera access is off for Room Planner.' : err.message });
      if (!denied) toast(`Could not start capture: ${err.message}`, { tone: 'danger' });
    }
  };

  const stop = async () => {
    if (!mod) return;
    setBusy('stop');
    try {
      await mod.stopCapture(); // resolves once RoomPlan has processed the final CapturedRoom
      const result: RoomPlanExport = (await mod.exportSkeleton()) ?? EMPTY_EXPORT;
      if (!result.skeleton?.walls?.length) {
        setProgress({ status: 'idle', message: result.meta?.reason });
        toast('The scan did not produce a closed room yet. Try walking the room slowly.', { tone: 'danger', ms: 4000 });
        return;
      }
      setScan(result);
      setProgress((p) => ({ ...p, status: 'done', message: undefined }));
    } catch (e) {
      setProgress({ status: 'error', message: (e as Error).message });
      toast((e as Error).message, { tone: 'danger', ms: 4500 });
    } finally {
      setBusy(null);
    }
  };

  // Hand the scan to /setup (space types + elements); the clean room is created there with seed:false.
  const useScan = () => {
    if (!scan) return;
    setRoomDraft({ name: 'Scanned room', source: 'scan', skeleton: scan.skeleton, objects: scan.objects });
    router.push('/setup');
  };

  const chipLabel =
    status === 'idle'
      ? 'Ready — point at a wall and press Start'
      : status === 'scanning'
        ? progress.message ?? 'Scanning… walk the room slowly'
        : status === 'processing'
          ? progress.message ?? 'Processing…'
          : status === 'done'
            ? 'Scan complete'
            : progress.message ?? 'Scan failed';
  const counts = `${progress.walls ?? 0} walls · ${progress.doors ?? 0} doors · ${progress.windows ?? 0} windows · ${progress.objects ?? 0} objects`;
  const dims = scan?.skeleton.dimensions;

  return (
    <View style={{ flex: 1, backgroundColor: '#000' }}>
      <RoomPlanView style={{ flex: 1 }} onCaptureStatus={onCaptureStatus} />
      <View style={[styles.scanBar, { paddingBottom: insets.bottom + spacing.md }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flexWrap: 'wrap' }}>
          <Chip
            icon={status === 'scanning' ? 'record-circle' : status === 'done' ? 'check-circle' : status === 'error' ? 'alert-circle' : 'cube-scan'}
            label={chipLabel}
            tone={status === 'scanning' ? 'danger' : status === 'done' ? 'accent' : 'tile'}
          />
          {status !== 'idle' ? <Text style={styles.counts}>{counts}</Text> : null}
        </View>

        {scan && dims ? (
          <Text style={styles.summary}>
            {formatDims(dims, units)} · {formatArea(dims.l, dims.w, units)} · {scan.objects.length} item{scan.objects.length === 1 ? '' : 's'} recognised
            {scan.meta?.skipped?.length ? ` · skipped ${scan.meta.skipped.join(', ')}` : ''}
          </Text>
        ) : null}

        {cameraDenied ? (
          <Button label="Open Settings to allow the camera" icon="cog" onPress={() => Linking.openSettings()} variant="secondary" style={{ marginTop: spacing.sm }} />
        ) : null}
        <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
          {status === 'done' && scan ? (
            <>
              <Button label="Rescan" icon="refresh" onPress={start} variant="secondary" style={{ flex: 1 }} disabled={busy !== null} />
              <Button label="Use this scan" icon="arrow-right-bold" onPress={useScan} disabled={busy !== null} style={{ flex: 2 }} />
            </>
          ) : (
            <>
              <Button
                label="Start"
                icon="play"
                onPress={start}
                disabled={status === 'scanning' || status === 'processing' || busy !== null}
                style={{ flex: 1 }}
                variant="secondary"
              />
              <Button label="Stop" icon="stop" onPress={stop} disabled={status !== 'scanning'} busy={busy === 'stop'} style={{ flex: 1 }} />
            </>
          )}
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
  const setRoomDraft = useStore((s) => s.setRoomDraft);
  const [busy, setBusy] = useState<'sample' | null>(null);
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

  const createManual = (dims: Dimensions, name: string) => {
    setSheetOpen(false);
    setRoomDraft({ name, source: 'manual', dimensions: dims, objects: [] });
    router.push('/setup');
  };

  const submitPasted = () => {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(pasted) as Record<string, unknown>;
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('not an object');
    } catch {
      toast('That is not valid JSON. Paste a RoomPlan export or our {skeleton, objects} JSON.', { tone: 'danger', ms: 4000 });
      return;
    }
    const draft = draftFromJson(parsed);
    if (!draft) {
      toast('That JSON has no "skeleton" or "dimensions", so there is no room to set up.', { tone: 'danger', ms: 4000 });
      return;
    }
    setRoomDraft(draft);
    router.push('/setup');
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
                Paste our {'{'}skeleton, objects{'}'} export (or {'{'}dimensions{'}'}). You will pick the space type next; the geometry is sent to POST /rooms unchanged.
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
              <Button label="Set up room from JSON" icon="upload" onPress={submitPasted} disabled={!pasted.trim()} style={{ marginTop: spacing.sm }} />
            </Tile>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>

      <DimensionsSheet visible={sheetOpen} units={units} onClose={() => setSheetOpen(false)} onSubmit={createManual} />
    </Screen>
  );
}

/** Pull the fields POST /rooms understands out of pasted JSON; `meta` from exportSkeleton() is debug-only. */
function draftFromJson(parsed: Record<string, unknown>): RoomDraft | null {
  const skeleton = parsed.skeleton as RoomDraft['skeleton'] | undefined;
  const dimensions = parsed.dimensions as RoomDraft['dimensions'] | undefined;
  if (!skeleton && !dimensions) return null;
  const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
  return {
    name: typeof parsed.name === 'string' && parsed.name.trim() ? parsed.name : 'Scanned room',
    source: skeleton ? 'scan' : 'manual',
    skeleton,
    dimensions: skeleton ? undefined : dimensions,
    doors: arr(parsed.doors),
    windows: arr(parsed.windows),
    objects: arr(parsed.objects),
  };
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
  counts: { color: colors.tile, fontSize: 13, fontWeight: '600' },
  summary: { color: colors.tile, fontSize: 13, marginTop: spacing.sm },
});
