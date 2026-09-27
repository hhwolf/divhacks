import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '../src/api';
import { DimensionsSheet } from '../src/components/DimensionsSheet';
import { useToast } from '../src/components/Toast';
import { BigCard, Chip, EmptyNote, IconButton, Screen, SectionTitle, Tile } from '../src/components/ui';
import { useStore } from '../src/store';
import { colors, radius, spacing, type } from '../src/theme';
import type { Dimensions, HealthResponse, RoomListEntry } from '../src/types';
import { formatArea, formatDims } from '../src/units';

export default function Home() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const { units, apiUrl, setRoomDraft } = useStore();

  const [rooms, setRooms] = useState<RoomListEntry[] | null>(null);
  const [health, setHealth] = useState<HealthResponse | null | 'down'>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState<'sample' | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const load = useCallback(async () => {
    const [r, h] = await Promise.allSettled([api.listRooms(), api.health()]);
    setRooms(r.status === 'fulfilled' ? r.value : []);
    setHealth(h.status === 'fulfilled' ? h.value : 'down');
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load, apiUrl]),
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const loadSample = async () => {
    setBusy('sample');
    try {
      const res = await api.createSampleRoom('nyc-bedroom');
      router.push(`/editor/${encodeURIComponent(res.currentLayout.id)}`);
    } catch (e) {
      toast(((e as Error | null)?.message ?? String(e)), { tone: 'danger', ms: 4500 });
    } finally {
      setBusy(null);
    }
  };

  // Manual rooms go through /setup (space types + elements) before POST /rooms creates the clean room.
  const createManual = (dims: Dimensions, name: string) => {
    setSheetOpen(false);
    setRoomDraft({ name, source: 'manual', dimensions: dims, objects: [] });
    router.push('/setup');
  };

  const modeLabel = health === null ? 'checking…' : health === 'down' ? 'API offline' : health.mode;
  const modeTone = health === null ? 'tile' : health === 'down' ? 'danger' : health.mode === 'live' ? 'accent' : 'tile';

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + spacing.xl }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.ink} />}
      >
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={type.title}>Adaptive Room Planner</Text>
            <Text style={type.subtitle}>Where did my space go?</Text>
          </View>
          <IconButton icon="cog" label="Settings" onPress={() => router.push('/settings')} />
        </View>

        <View style={{ gap: spacing.md }}>
          <BigCard
            icon="cube-scan"
            title="Scan room"
            subtitle="LiDAR scan with RoomPlan (iPhone Pro, dev build)"
            onPress={() => router.push('/scan')}
          />
          <BigCard
            icon="bed-king-outline"
            title="Load sample room"
            subtitle="NYC bedroom, 11' × 10' with a door and a window"
            onPress={loadSample}
            busy={busy === 'sample'}
          />
          <BigCard
            icon="ruler-square"
            title="Enter dimensions"
            subtitle={units === 'metric' ? 'Length, width and height in meters' : 'Length, width and height in feet and inches'}
            onPress={() => setSheetOpen(true)}
          />
        </View>

        <View style={{ marginTop: spacing.xl }}>
          <SectionTitle right={rooms && rooms.length > 0 ? <Text style={type.small}>{rooms.length} total</Text> : null}>Recent rooms</SectionTitle>
          <Tile style={{ padding: spacing.sm }}>
            {rooms === null ? (
              <EmptyNote>Loading…</EmptyNote>
            ) : rooms.length === 0 ? (
              <EmptyNote>{health === 'down' ? `No connection to ${apiUrl}. Open Settings to fix the API URL.` : 'No rooms yet. Scan, load the sample, or enter dimensions.'}</EmptyNote>
            ) : (
              rooms.slice(0, 12).map((room, i) => (
                <Pressable
                  key={room.id}
                  onPress={() => router.push(`/variants/${encodeURIComponent(room.id)}`)}
                  style={({ pressed }) => [styles.roomRow, i > 0 && styles.roomRowBorder, pressed && { opacity: 0.7 }]}
                >
                  <View style={styles.roomIcon}>
                    <MaterialCommunityIcons
                      name={room.source === 'scan' ? 'cube-scan' : room.source === 'sample' ? 'bed-king-outline' : 'ruler-square'}
                      size={20}
                      color={colors.tile}
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.roomName} numberOfLines={1}>
                      {room.name}
                    </Text>
                    <Text style={type.small} numberOfLines={1}>
                      {formatDims(room.skeleton?.dimensions, units)}
                      {room.skeleton?.dimensions ? ` · ${formatArea(room.skeleton.dimensions.l, room.skeleton.dimensions.w, units)}` : ''}
                    </Text>
                  </View>
                  {typeof room.layoutCount === 'number' ? (
                    <Chip label={`${room.layoutCount} layout${room.layoutCount === 1 ? '' : 's'}`} tone="tile" style={{ backgroundColor: colors.tileMuted }} />
                  ) : null}
                  <MaterialCommunityIcons name="chevron-right" size={22} color={colors.inkSoft} />
                </Pressable>
              ))
            )}
          </Tile>
        </View>

        <View style={styles.footer}>
          <Chip icon={health === 'down' ? 'cloud-off-outline' : health !== null && health.mode === 'live' ? 'cloud-check-outline' : 'flask-outline'} label={`API: ${modeLabel}`} tone={modeTone} onPress={() => router.push('/settings')} />
          <Text style={[type.small, { marginLeft: spacing.sm }]} numberOfLines={1}>
            {apiUrl.replace(/^https?:\/\//, '')}
          </Text>
        </View>
      </ScrollView>

      <DimensionsSheet visible={sheetOpen} units={units} onClose={() => setSheetOpen(false)} onSubmit={createManual} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: spacing.lg },
  headerRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: spacing.xl, gap: spacing.md },
  roomRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, padding: spacing.sm, borderRadius: radius.sm },
  roomRowBorder: { borderTopWidth: 1, borderTopColor: colors.tileMuted },
  roomIcon: { width: 40, height: 40, borderRadius: radius.sm, backgroundColor: colors.accentDeep, alignItems: 'center', justifyContent: 'center' },
  roomName: { fontSize: 15, fontWeight: '700', color: colors.ink },
  footer: { flexDirection: 'row', alignItems: 'center', marginTop: spacing.xl },
});
