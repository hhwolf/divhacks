import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import React, { useCallback, useState } from 'react';
import { Alert, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '../../src/api';
import { useToast } from '../../src/components/Toast';
import { Button, Chip, EmptyNote, Screen, Tile } from '../../src/components/ui';
import { useStore } from '../../src/store';
import { SPACE_TYPES } from '../../src/setupVocab';
import { colors, radius, spacing, type } from '../../src/theme';
import type { Layout, Room } from '../../src/types';
import { formatArea, formatDims } from '../../src/units';

export default function Variants() {
  const router = useRouter();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const units = useStore((s) => s.units);
  const { roomId } = useLocalSearchParams<{ roomId: string }>();

  const [room, setRoom] = useState<Room | null>(null);
  const [layouts, setLayouts] = useState<Layout[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!roomId) return;
    try {
      const res = await api.getRoom(roomId);
      setRoom(res.room);
      const sorted = [...res.layouts].sort((a, b) => Number(b.isCurrent) - Number(a.isCurrent) || (a.createdAt ?? '').localeCompare(b.createdAt ?? ''));
      setLayouts(sorted);
    } catch (e) {
      toast(((e as Error | null)?.message ?? String(e)), { tone: 'danger', ms: 4500 });
      setLayouts([]);
    }
  }, [roomId, toast]);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const current = layouts?.find((l) => l.isCurrent) ?? null;

  const run = async (id: string, fn: () => Promise<unknown>, okMsg?: string) => {
    setBusyId(id);
    try {
      await fn();
      if (okMsg) toast(okMsg);
      await load();
    } catch (e) {
      toast(((e as Error | null)?.message ?? String(e)), { tone: 'danger', ms: 4500 });
    } finally {
      setBusyId(null);
    }
  };

  const rename = (l: Layout) => {
    const apply = (name?: string) => {
      const n = (name ?? '').trim();
      if (!n || n === l.name) return;
      void run(l.id, () => api.updateLayout(l, { name: n }), `Renamed to “${n}”`);
    };
    if (Platform.OS === 'ios') {
      Alert.prompt('Rename variant', undefined, [{ text: 'Cancel', style: 'cancel' }, { text: 'Save', onPress: apply }], 'plain-text', l.name);
    } else {
      toast('Rename is available on iOS; use the web editor tab bar on Android.');
    }
  };

  const duplicate = (l: Layout) => {
    const suggested = `${l.name} copy`;
    const apply = (name?: string) => {
      const n = (name ?? '').trim() || suggested;
      void run(l.id, async () => {
        const forked = await api.forkLayout(l.id, n);
        toast(`Created “${forked.name}”`);
      });
    };
    if (Platform.OS === 'ios') {
      Alert.prompt('Duplicate variant', 'Name for the copy', [{ text: 'Cancel', style: 'cancel' }, { text: 'Duplicate', onPress: apply }], 'plain-text', suggested);
    } else {
      apply(suggested);
    }
  };

  const remove = (l: Layout) => {
    Alert.alert('Delete variant?', `“${l.name}” will be removed. The Current Room is never deleted.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => void run(l.id, () => api.deleteLayout(l.id), 'Deleted') },
    ]);
  };

  const dims = room?.skeleton?.dimensions;

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + spacing.xl }]}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => {
              setRefreshing(true);
              await load();
              setRefreshing(false);
            }}
            tintColor={colors.ink}
          />
        }
      >
        <View style={{ marginBottom: spacing.lg }}>
          <Text style={type.title} numberOfLines={1}>
            {room?.name ?? 'Room'}
          </Text>
          <Text style={type.subtitle}>
            {dims ? `${formatDims(dims, units)} · ${formatArea(dims.l, dims.w, units)}` : ' '}
            {room?.source ? ` · ${room.source}` : ''}
          </Text>
          {room ? (
            <View style={styles.setupRow}>
              {(room.spaceTypes ?? []).map((t) => (
                <Chip key={t} label={SPACE_TYPES.find((s) => s.id === t)?.label ?? t} tone="ink" />
              ))}
              <Chip
                icon="tune-variant"
                label={room.spaceTypes?.length ? 'Edit setup' : 'Set up space'}
                onPress={() => router.push({ pathname: '/setup', params: { roomId: room.id } })}
                style={styles.chipOutline}
              />
            </View>
          ) : null}
        </View>

        <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.lg }}>
          <Button
            label="Ask the planner"
            icon="chat-question-outline"
            onPress={() => router.push({ pathname: '/ask', params: { roomId: roomId ?? '', layoutId: current?.id ?? '' } })}
            disabled={!current}
            style={{ flex: 1 }}
          />
        </View>

        {layouts === null ? (
          <Tile>
            <EmptyNote>Loading…</EmptyNote>
          </Tile>
        ) : layouts.length === 0 ? (
          <Tile>
            <EmptyNote>No layouts found for this room.</EmptyNote>
          </Tile>
        ) : (
          <View style={{ gap: spacing.md }}>
            {layouts.map((l) => (
              <Tile key={l.id} style={[styles.card, l.isCurrent && styles.currentCard]}>
                <Pressable onPress={() => router.push(`/editor/${encodeURIComponent(l.id)}`)} style={styles.cardHeader}>
                  <View style={[styles.badge, { backgroundColor: l.isCurrent ? colors.ink : l.createdBy === 'agent' ? colors.accentDeep : colors.bgDeep }]}>
                    <MaterialCommunityIcons name={l.isCurrent ? 'lock' : l.createdBy === 'agent' ? 'robot-outline' : 'floor-plan'} size={20} color={colors.tile} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.cardTitle} numberOfLines={1}>
                      {l.isCurrent ? 'Current Room' : l.name}
                    </Text>
                    <Text style={type.small} numberOfLines={1}>
                      {l.items.length} item{l.items.length === 1 ? '' : 's'}
                      {l.metrics ? ` · ${Math.round(l.metrics.openFloor * (l.metrics.openFloor <= 1 ? 100 : 1))}% open · ${l.metrics.conflicts} conflict${l.metrics.conflicts === 1 ? '' : 's'}` : ''}
                      {l.isCurrent ? ' · only you can change it' : l.requestText ? ` · “${l.requestText}”` : ''}
                    </Text>
                  </View>
                  <MaterialCommunityIcons name="chevron-right" size={22} color={colors.inkSoft} />
                </Pressable>

                <View style={styles.actions}>
                  <Chip icon="open-in-app" label="Open" tone="ink" onPress={() => router.push(`/editor/${encodeURIComponent(l.id)}`)} />
                  <Chip icon="content-copy" label="Duplicate" onPress={() => duplicate(l)} style={styles.chipOutline} />
                  {!l.isCurrent ? (
                    <>
                      <Chip icon="pencil-outline" label="Rename" onPress={() => rename(l)} style={styles.chipOutline} />
                      <Chip icon="trash-can-outline" label={busyId === l.id ? '…' : 'Delete'} tone="danger" onPress={() => remove(l)} />
                      {current ? (
                        <Chip
                          icon="compare-horizontal"
                          label="Compare with Current"
                          tone="accent"
                          onPress={() => router.push({ pathname: '/compare/[a]/[b]', params: { a: current.id, b: l.id, roomId: roomId ?? '' } })}
                        />
                      ) : null}
                    </>
                  ) : null}
                </View>
              </Tile>
            ))}
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  card: { padding: spacing.md },
  currentCard: { borderWidth: 2, borderColor: colors.ink },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  badge: { width: 40, height: 40, borderRadius: radius.sm, alignItems: 'center', justifyContent: 'center' },
  cardTitle: { fontSize: 16, fontWeight: '700', color: colors.ink },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.md },
  setupRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.sm },
  chipOutline: { borderWidth: 1, borderColor: colors.tileMuted },
});
