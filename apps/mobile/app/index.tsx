import { MaterialCommunityIcons } from '@expo/vector-icons';
import { Redirect, useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Modal, Pressable, RefreshControl, ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '../src/api';
import { sampleRoomDraft } from '../src/newRoom';
import { DimensionsSheet } from '../src/components/DimensionsSheet';
import { RenameSheet } from '../src/components/RenameSheet';
import { useToast } from '../src/components/Toast';
import { EmptyNote, IconButton, Screen } from '../src/components/ui';
import { useStore } from '../src/store';
import { colors, radius, shadow, spacing, type } from '../src/theme';
import type { Dimensions, RoomListEntry } from '../src/types';
import { formatLength } from '../src/units';

export default function Home() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const toast = useToast();
  const { units, apiUrl, setRoomDraft, onboarded } = useStore();

  const [rooms, setRooms] = useState<RoomListEntry[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState<'sample' | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [renaming, setRenaming] = useState<RoomListEntry | null>(null);
  const [savingName, setSavingName] = useState(false);
  const [actionsFor, setActionsFor] = useState<RoomListEntry | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try { setRooms([...(await api.listRooms())].reverse()); } catch { setRooms([]); }
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load, apiUrl]));

  const loadSample = async () => {
    setBusy('sample');
    try {
      setRoomDraft(sampleRoomDraft());
      router.push('/setup');
    } catch (e) {
      toast((e as Error | null)?.message ?? 'Something went wrong', { tone: 'danger', ms: 4500 });
    } finally {
      setBusy(null);
    }
  };

  // Typed dimensions go through the same "what is this space for?" setup as a scan.
  const startManual = (dims: Dimensions, name: string) => {
    setSheetOpen(false);
    setRoomDraft({ source: 'manual', dimensions: dims, objects: [], name });
    router.push('/setup');
  };

  const deleteRoom = async () => {
    const room = actionsFor; if (!room) return;
    setDeleting(true);
    try {
      await api.deleteRoom(room.id);
      setRooms((rs) => rs?.filter((r) => r.id !== room.id) ?? rs);
      toast(`Deleted “${room.name}”`);
      setActionsFor(null);
    } catch (e) {
      toast((e as Error | null)?.message ?? 'Something went wrong', { tone: 'danger', ms: 4500 });
    } finally {
      setDeleting(false);
    }
  };

  const saveName = async (name: string) => {
    if (!renaming) return;
    setSavingName(true);
    try {
      await api.updateRoom(renaming.id, { name });
      setRooms((rs) => rs?.map((r) => (r.id === renaming.id ? { ...r, name } : r)) ?? rs);
      toast(`Renamed to “${name}”`);
      setRenaming(null);
    } catch (e) {
      toast((e as Error | null)?.message ?? 'Something went wrong', { tone: 'danger', ms: 4500 });
    } finally {
      setSavingName(false);
    }
  };

  if (!onboarded) return <Redirect href="/welcome" />;


  return (
    <Screen>
      <ScrollView
        contentContainerStyle={{ paddingBottom: insets.bottom + spacing.xl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} tintColor={colors.forest} />}
      >
        {/* First screen: brand + the three ways in, centered. Rooms live below the fold. */}
        <View style={[styles.hero, { minHeight: height - insets.bottom, paddingTop: insets.top + spacing.md }]}>
          <View style={styles.brandRow}>
            <View style={styles.mark}><MaterialCommunityIcons name="leaf" size={18} color={colors.white} /></View>
            <Text style={styles.brand}>FitCheck</Text>
            <View style={{ flex: 1 }} />
            <IconButton icon="cog-outline" label="Settings" onPress={() => router.push('/settings')} />
          </View>

          <View style={styles.center}>
            <Pressable onPress={() => router.push('/scan')} accessibilityRole="button" accessibilityLabel="Scan room" style={({ pressed }) => [styles.scanCard, pressed && styles.pressed]}>
              <View style={styles.scanMark}><MaterialCommunityIcons name="cube-scan" size={40} color={colors.white} /></View>
              <Text style={styles.scanTitle}>Scan room</Text>
              <View style={styles.scanCta}><Text style={styles.scanCtaText}>Start scan</Text><MaterialCommunityIcons name="arrow-right" size={16} color={colors.forest} /></View>
            </Pressable>

            <Pressable onPress={loadSample} disabled={busy !== null} accessibilityRole="button" accessibilityLabel="Load sample room" style={({ pressed }) => [styles.rowCard, styles.sampleCard, pressed && styles.pressed]}>
              <View style={[styles.rowIcon, { backgroundColor: colors.accentDeep }]}>
                {busy === 'sample' ? <ActivityIndicator color={colors.white} /> : <MaterialCommunityIcons name="bed-outline" size={22} color={colors.white} />}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>Load sample room</Text>
                <Text style={type.small}>L-shaped loft</Text>
              </View>
              <MaterialCommunityIcons name="chevron-right" size={22} color={colors.accentDeep} />
            </Pressable>

            <Pressable onPress={() => setSheetOpen(true)} accessibilityRole="button" accessibilityLabel="Enter dimensions" style={({ pressed }) => [styles.rowCard, styles.dimsCard, pressed && styles.pressed]}>
              <View style={[styles.rowIcon, { backgroundColor: colors.sageTint }]}>
                <MaterialCommunityIcons name="ruler-square" size={22} color={colors.forest} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>Enter dimensions</Text>
                <Text style={type.small}>Length × width × height</Text>
              </View>
              <MaterialCommunityIcons name="chevron-right" size={22} color={colors.inkSoft} />
            </Pressable>
          </View>
        </View>

        {/* Below the fold: one grouped list — name + dimensions; ⋯ for rename / delete. */}
        <View style={styles.roomsSection}>
          <View style={styles.sectionRow}>
            <Text style={type.h2}>Your rooms</Text>
            {rooms?.length ? <Text style={type.small}>{rooms.length}</Text> : null}
          </View>
          {rooms === null ? (
            <EmptyNote>Loading…</EmptyNote>
          ) : rooms.length === 0 ? (
            <View style={styles.group}><EmptyNote>No rooms yet</EmptyNote></View>
          ) : (
            <View style={styles.group}>
              {rooms.slice(0, 20).map((room, i) => (
                <Pressable key={room.id} onPress={() => router.push(`/variants/${encodeURIComponent(room.id)}`)} style={({ pressed }) => [styles.roomRow, i > 0 && styles.roomDivider, pressed && { backgroundColor: colors.bg }]}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.roomName} numberOfLines={1}>{room.name}</Text>
                    <Text style={type.small} numberOfLines={1}>
                      {room.skeleton?.dimensions ? `${formatLength(room.skeleton.dimensions.l, units)} × ${formatLength(room.skeleton.dimensions.w, units)}` : '—'}
                    </Text>
                  </View>
                  <Pressable onPress={() => setActionsFor(room)} hitSlop={10} accessibilityRole="button" accessibilityLabel={`Options for ${room.name}`} style={({ pressed }) => [styles.moreBtn, pressed && styles.pressed]}>
                    <MaterialCommunityIcons name="dots-horizontal" size={20} color={colors.inkSoft} />
                  </Pressable>
                </Pressable>
              ))}
            </View>
          )}
        </View>
      </ScrollView>

      <DimensionsSheet visible={sheetOpen} units={units} onClose={() => setSheetOpen(false)} onSubmit={startManual} />
      <RenameSheet visible={renaming !== null} title="Rename room" initial={renaming?.name ?? ''} busy={savingName} onClose={() => setRenaming(null)} onSave={saveName} />
      <RoomActionsSheet
        room={actionsFor}
        busy={deleting}
        onClose={() => setActionsFor(null)}
        onRename={() => { setRenaming(actionsFor); setActionsFor(null); }}
        onDelete={deleteRoom}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  hero: { paddingHorizontal: spacing.lg, justifyContent: 'space-between' },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  mark: { width: 32, height: 32, borderRadius: 9, backgroundColor: colors.forest, alignItems: 'center', justifyContent: 'center' },
  brand: { fontSize: 17, fontWeight: '700', color: colors.ink, letterSpacing: -0.2 },
  center: { flex: 1, justifyContent: 'center', paddingVertical: spacing.xl },
  pressed: { opacity: 0.85, transform: [{ scale: 0.99 }] },
  scanCard: { backgroundColor: colors.forest, borderRadius: radius.lg + 4, padding: spacing.xl, alignItems: 'center', ...shadow.soft },
  scanMark: { width: 76, height: 76, borderRadius: 20, borderWidth: 2, borderColor: 'rgba(255,255,255,0.85)', alignItems: 'center', justifyContent: 'center', marginBottom: spacing.md },
  scanTitle: { color: colors.white, fontSize: 26, fontWeight: '700', letterSpacing: -0.4 },
  scanSub: { color: 'rgba(255,255,255,0.78)', fontSize: 14, textAlign: 'center', marginTop: 4, lineHeight: 20 },
  scanCta: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.white, borderRadius: radius.pill, paddingHorizontal: 18, paddingVertical: 10, marginTop: spacing.lg },
  scanCtaText: { color: colors.forest, fontWeight: '700', fontSize: 15 },
  rowCard: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, borderRadius: radius.lg, padding: spacing.lg, marginTop: spacing.md },
  sampleCard: { backgroundColor: colors.sageTint, marginTop: spacing.xl + spacing.lg },
  dimsCard: { backgroundColor: colors.tile, borderWidth: 1, borderColor: colors.tileMuted },
  rowIcon: { width: 44, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  rowTitle: { fontSize: 16, fontWeight: '700', color: colors.ink, marginBottom: 2 },
  roomsSection: { paddingHorizontal: spacing.lg, paddingTop: spacing.xl },
  sectionRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: spacing.sm, paddingHorizontal: 4 },
  group: { backgroundColor: colors.tile, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.tileMuted, overflow: 'hidden' },
  roomRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: 14, paddingLeft: spacing.lg, paddingRight: spacing.sm },
  roomDivider: { borderTopWidth: 1, borderTopColor: colors.tileMuted },
  roomName: { fontSize: 16, fontWeight: '600', color: colors.ink, marginBottom: 2 },
  moreBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
});

/** Bottom sheet for a room row: Rename, Delete (with a confirm step). Cross-platform (no Alert buttons on web). */
function RoomActionsSheet({ room, busy, onClose, onRename, onDelete }: { room: RoomListEntry | null; busy: boolean; onClose: () => void; onRename: () => void; onDelete: () => void }) {
  const insets = useSafeAreaInsets();
  const [confirm, setConfirm] = useState(false);
  useEffect(() => { setConfirm(false); }, [room?.id]);
  const close = () => { if (!busy) { setConfirm(false); onClose(); } };
  return (
    <Modal visible={room !== null} transparent animationType="fade" onRequestClose={close}>
      <Pressable style={sheet.backdrop} onPress={close} accessibilityLabel="Close">
        <Pressable style={[sheet.card, { paddingBottom: insets.bottom + spacing.lg }]} onPress={() => {}}>
          <Text style={sheet.title} numberOfLines={1}>{room?.name}</Text>
          {confirm ? (
            <>
              <Text style={[type.small, { marginBottom: spacing.md }]}>Delete this room and its layouts?</Text>
              <Pressable onPress={onDelete} disabled={busy} style={({ pressed }) => [sheet.action, sheet.danger, pressed && { opacity: 0.85 }]}>
                {busy ? <ActivityIndicator color={colors.white} /> : <Text style={[sheet.actionText, { color: colors.white }]}>Delete room</Text>}
              </Pressable>
              <Pressable onPress={() => setConfirm(false)} disabled={busy} style={({ pressed }) => [sheet.action, pressed && { opacity: 0.85 }]}><Text style={sheet.actionText}>Cancel</Text></Pressable>
            </>
          ) : (
            <>
              <Pressable onPress={() => { setConfirm(false); onRename(); }} style={({ pressed }) => [sheet.action, pressed && { opacity: 0.85 }]}>
                <MaterialCommunityIcons name="pencil-outline" size={18} color={colors.ink} /><Text style={sheet.actionText}>Rename</Text>
              </Pressable>
              <Pressable onPress={() => setConfirm(true)} style={({ pressed }) => [sheet.action, pressed && { opacity: 0.85 }]}>
                <MaterialCommunityIcons name="trash-can-outline" size={18} color={colors.danger} /><Text style={[sheet.actionText, { color: colors.danger }]}>Delete room</Text>
              </Pressable>
            </>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const sheet = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(37,52,32,0.35)', justifyContent: 'flex-end' },
  card: { backgroundColor: colors.tile, borderTopLeftRadius: radius.lg + 4, borderTopRightRadius: radius.lg + 4, padding: spacing.lg, gap: spacing.sm },
  title: { fontSize: 17, fontWeight: '700', color: colors.ink, marginBottom: spacing.xs },
  action: { flexDirection: 'row', gap: spacing.sm, alignItems: 'center', justifyContent: 'center', height: 50, borderRadius: radius.md, backgroundColor: colors.bg },
  actionText: { fontSize: 16, fontWeight: '600', color: colors.ink },
  danger: { backgroundColor: colors.danger },
});
