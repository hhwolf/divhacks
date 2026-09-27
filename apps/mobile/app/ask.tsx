import { MaterialCommunityIcons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '../src/api';
import { useToast } from '../src/components/Toast';
import { Button, Chip, EmptyNote, Screen, SectionTitle, Tile } from '../src/components/ui';
import { type AgentLogEntry, useStore } from '../src/store';
import { colors, radius, spacing, type } from '../src/theme';
import type { AgentStatus, Layout } from '../src/types';

const PLACEHOLDER = 'Will this fit beside my window without moving my bed?';

export default function Ask() {
  const router = useRouter();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ roomId?: string; layoutId?: string }>();
  const { agentLog, pushAgentLog, updateAgentLog } = useStore();

  const [roomId, setRoomId] = useState(params.roomId ?? '');
  const [baseLayoutId, setBaseLayoutId] = useState(params.layoutId ?? '');
  const [baseLayout, setBaseLayout] = useState<Layout | null>(null);
  const [text, setText] = useState('');
  const [furniture, setFurniture] = useState<{ id: string; name: string } | null>(null);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Resolve missing ids: layout -> room, or room -> its Current layout.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (baseLayoutId) {
          const l = await api.getLayout(baseLayoutId);
          if (cancelled) return;
          setBaseLayout(l);
          if (!roomId) setRoomId(l.roomId);
        } else if (roomId) {
          const { layouts } = await api.getRoom(roomId);
          if (cancelled) return;
          const current = layouts.find((l) => l.isCurrent) ?? layouts[0];
          if (current) {
            setBaseLayout(current);
            setBaseLayoutId(current.id);
          }
        }
      } catch (e) {
        if (!cancelled) toast((e as Error).message, { tone: 'danger' });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [baseLayoutId, roomId, toast]);

  const pasteLink = () => {
    const apply = (url?: string) => {
      const u = (url ?? '').trim();
      if (!u) return;
      setText((t) => (t.trim() ? `${t.trim()} ${u}` : u));
    };
    if (Platform.OS === 'ios') {
      Alert.prompt('Paste a product link', 'The planner will read the listing to size the item.', [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Add', onPress: (v?: string) => apply(v) },
      ]);
    } else {
      // Alert.prompt is iOS-only; on Android the user can paste straight into the text box.
      toast('Paste the link directly into the request box.');
    }
  };

  const pickPhoto = async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        toast('Photo library permission is needed to attach a photo.', { tone: 'danger' });
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.7, allowsEditing: false });
      if (result.canceled || !result.assets[0]) return;
      const asset = result.assets[0];
      setUploading(true);
      const item = await api.furnitureFromPhoto({
        uri: asset.uri,
        name: asset.fileName ?? `photo-${Date.now()}.jpg`,
        type: asset.mimeType ?? 'image/jpeg',
      });
      setFurniture({ id: item.id, name: item.name ?? 'Photo item' });
      toast(`Attached ${item.name ?? 'photo item'}${item.estimated ? ' (estimated size)' : ''}`);
    } catch (e) {
      toast(`Photo upload failed: ${(e as Error).message}`, { tone: 'danger', ms: 4500 });
    } finally {
      setUploading(false);
    }
  };

  const send = async () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (!roomId || !baseLayoutId) {
      toast('Open a room first so the planner knows which layout to start from.', { tone: 'danger' });
      return;
    }
    const entry: AgentLogEntry = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      at: Date.now(),
      text: trimmed,
      roomId,
      baseLayoutId,
      furnitureId: furniture?.id,
      pending: true,
    };
    pushAgentLog(entry);
    setSending(true);
    setText('');
    setFurniture(null);
    try {
      const res = await api.agentRequest({ text: trimmed, roomId, baseLayoutId, furnitureId: entry.furnitureId });
      updateAgentLog(entry.id, { pending: false, response: res });
    } catch (e) {
      updateAgentLog(entry.id, { pending: false, error: (e as Error).message });
    } finally {
      setSending(false);
    }
  };

  const simulateIMessage = () => {
    Alert.alert(
      'Ask over iMessage (Photon)',
      'In production you text the same request to our Photon iMessage line. Photon POSTs it to /webhooks/photon, the agent runs the identical plan → solver → validate pipeline, and replies with one sentence plus roomplanner://layout/{id} and a web link. In mock mode the API answers with a canned plan, so this screen exercises the exact same path via POST /agent/request with channel "app".',
      [{ text: 'Got it' }],
    );
  };

  const visibleLog = agentLog.filter((e) => !roomId || e.roomId === roomId);

  return (
    <Screen>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }} keyboardVerticalOffset={insets.top + 44}>
        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + spacing.xl }]} keyboardShouldPersistTaps="handled">
          <Tile>
            <View style={styles.baseRow}>
              <MaterialCommunityIcons name="floor-plan" size={16} color={colors.inkSoft} />
              <Text style={type.small} numberOfLines={1}>
                {baseLayout ? (baseLayout.isCurrent ? 'Starting from the Current Room (never modified)' : `Starting from “${baseLayout.name}”`) : roomId ? 'Loading layout…' : 'No room selected'}
              </Text>
            </View>
            <TextInput
              multiline
              value={text}
              onChangeText={setText}
              placeholder={PLACEHOLDER}
              placeholderTextColor="#9AA392"
              style={styles.input}
              editable={!sending}
            />
            <View style={styles.chipRow}>
              <Chip icon="link-variant" label="Paste link" onPress={pasteLink} tone="tile" style={styles.chipOutline} />
              <Chip icon="camera-outline" label={uploading ? 'Uploading…' : furniture ? `Photo: ${furniture.name}` : 'Photo'} onPress={uploading ? undefined : pickPhoto} tone={furniture ? 'accent' : 'tile'} style={styles.chipOutline} />
              {furniture ? <Chip icon="close" label="Remove" onPress={() => setFurniture(null)} tone="tile" style={styles.chipOutline} /> : null}
            </View>
            <Button label="Send" icon="send" onPress={send} busy={sending} disabled={!text.trim() || !baseLayoutId} style={{ marginTop: spacing.md }} />
            <Pressable onPress={simulateIMessage} style={{ alignSelf: 'center', marginTop: spacing.md }}>
              <Text style={styles.link}>Simulate iMessage (Photon)</Text>
            </Pressable>
          </Tile>

          <View style={{ marginTop: spacing.xl }}>
            <SectionTitle>Agent log</SectionTitle>
            {visibleLog.length === 0 ? (
              <Tile>
                <EmptyNote>No requests yet. Try “{PLACEHOLDER}” or “make space for yoga, keep my dresser”.</EmptyNote>
              </Tile>
            ) : (
              <View style={{ gap: spacing.sm }}>
                {visibleLog.map((e) => (
                  <LogCard key={e.id} entry={e} onOpen={(id) => router.push(`/editor/${encodeURIComponent(id)}`)} />
                ))}
              </View>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

function statusTone(s: AgentStatus | undefined, error?: string): 'accent' | 'warn' | 'danger' | 'tile' {
  if (error) return 'danger';
  if (s === 'ok') return 'accent';
  if (s === 'clarify') return 'warn';
  if (s === 'rejected') return 'danger';
  return 'tile';
}

function LogCard({ entry, onOpen }: { entry: AgentLogEntry; onOpen: (layoutId: string) => void }) {
  const res = entry.response;
  const status = entry.pending ? 'thinking…' : entry.error ? 'error' : res?.status ?? 'unknown';
  return (
    <Tile style={{ padding: spacing.md }}>
      <View style={styles.logHeader}>
        <Text style={[type.body, { flex: 1, fontWeight: '600' }]}>{entry.text}</Text>
        <Chip label={status} tone={entry.pending ? 'tile' : statusTone(res?.status, entry.error)} />
      </View>
      {entry.furnitureId ? <Text style={type.small}>with photo item {entry.furnitureId}</Text> : null}
      {entry.error ? <Text style={[type.small, { color: colors.danger, marginTop: 6 }]}>{entry.error}</Text> : null}
      {res ? (
        <>
          <Text style={[type.body, { marginTop: 6 }]}>{res.reply}</Text>
          {res.plan?.clarifyingQuestion && res.plan.clarifyingQuestion !== res.reply ? (
            <Text style={[type.small, { marginTop: 4, fontStyle: 'italic' }]}>{res.plan.clarifyingQuestion}</Text>
          ) : null}
          {res.layout ? (
            <Button
              label={`Open variant “${res.layout.name}”`}
              icon="open-in-new"
              variant="secondary"
              onPress={() => onOpen(res.layout!.id)}
              style={{ marginTop: spacing.sm, backgroundColor: colors.tileMuted }}
            />
          ) : null}
        </>
      ) : null}
    </Tile>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  baseRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: spacing.sm },
  input: {
    minHeight: 96,
    backgroundColor: colors.white,
    borderRadius: radius.sm,
    padding: spacing.md,
    fontSize: 16,
    color: colors.ink,
    textAlignVertical: 'top',
  },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.sm },
  chipOutline: { borderWidth: 1, borderColor: colors.tileMuted },
  link: { color: colors.inkSoft, textDecorationLine: 'underline', fontSize: 13 },
  logHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm },
});
