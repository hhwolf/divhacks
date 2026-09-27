import { MaterialCommunityIcons } from '@expo/vector-icons';
import { Stack, useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import * as ScreenOrientation from 'expo-screen-orientation';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '../src/api';
import { useToast } from '../src/components/Toast';
import { Button, Chip, EmptyNote, Field, type IconName, Screen, Tile } from '../src/components/ui';
import { ELEMENTS, localSuggestions, slugify, SPACE_TYPE_ICONS, SPACE_TYPES, SUGGESTIONS } from '../src/setupVocab';
import { useStore } from '../src/store';
import { colors, radius, spacing, type } from '../src/theme';
import type { RoomElement, SetupSuggestionsResponse, SpaceTypeInfo } from '../src/types';
import { formatArea, formatDims } from '../src/units';

type Step = 1 | 2;

/**
 * Room setup: "What kind of space is this?" → "What does this room need?" → create the clean base room.
 * Create mode reads the draft from the store (set by scan / dimensions / paste). `?roomId=` opens edit mode,
 * pre-filled from the room and saved with PATCH /rooms/{id}/setup.
 */
export default function Setup() {
  const router = useRouter();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const units = useStore((s) => s.units);
  const draft = useStore((s) => s.roomDraft);
  const setRoomDraft = useStore((s) => s.setRoomDraft);
  const { roomId } = useLocalSearchParams<{ roomId?: string }>();
  const editMode = Boolean(roomId);

  const [step, setStep] = useState<Step>(1);
  const [name, setName] = useState(draft?.name ?? '');
  const [spaceTypes, setSpaceTypes] = useState<SpaceTypeInfo[]>(SPACE_TYPES);
  const [selected, setSelected] = useState<string[]>([]);
  const [pool, setPool] = useState<SetupSuggestionsResponse | null>(null);
  const [poolLoading, setPoolLoading] = useState(false);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [custom, setCustom] = useState<RoomElement[]>([]);
  const [customText, setCustomText] = useState('');
  const [busy, setBusy] = useState(false);
  const [roomState, setRoomState] = useState<'idle' | 'loading' | 'ready' | 'missing'>(editMode ? 'loading' : 'idle');
  const [roomName, setRoomName] = useState<string | null>(null);
  const [roomDims, setRoomDims] = useState<{ l: number; w: number; h: number } | undefined>(draft?.skeleton?.dimensions ?? draft?.dimensions);
  const [detectedCount, setDetectedCount] = useState(draft?.objects.length ?? 0);

  // Portrait form. The editor locks landscape while focused; a cold deep link into /setup would otherwise inherit it.
  useFocusEffect(
    useCallback(() => {
      ScreenOrientation.lockAsync(ScreenOrientation.OrientationLock.PORTRAIT_UP).catch(() => {});
    }, []),
  );

  // Ids the API suggested on the previous load. Null until the first load so we can tell "first time" apart.
  const seenSuggested = useRef<Set<string> | null>(null);
  // In edit mode the user already chose; only newly suggested elements get auto-checked afterwards.
  const prefilled = useRef(false);

  useEffect(() => {
    api
      .getSpaceTypes()
      .then((list) => {
        if (Array.isArray(list) && list.length) setSpaceTypes(list);
      })
      .catch(() => {}); // older API: keep the local vocabulary
  }, []);

  useEffect(() => {
    if (!roomId) return;
    let cancelled = false;
    api
      .getRoom(roomId)
      .then(({ room }) => {
        if (cancelled) return;
        const elements = room.elements ?? [];
        setRoomName(room.name);
        setRoomDims(room.skeleton?.dimensions);
        setDetectedCount(room.detectedObjects?.length ?? 0);
        setSelected(room.spaceTypes ?? []);
        setCustom(elements.filter((e) => e.custom));
        setChecked(new Set(elements.map((e) => e.id)));
        prefilled.current = true;
        setRoomState('ready');
      })
      .catch((e: Error | null) => {
        if (cancelled) return;
        toast(e?.message ?? String(e), { tone: 'danger', ms: 4500 });
        setRoomState('missing');
      });
    return () => {
      cancelled = true;
    };
  }, [roomId, toast]);

  const loadPool = useCallback(async (types: string[]) => {
    setPoolLoading(true);
    let next: SetupSuggestionsResponse;
    try {
      next = await api.getSetupSuggestions(types);
      if (!Array.isArray(next?.suggested) || !Array.isArray(next?.all)) throw new Error('bad shape');
    } catch {
      next = localSuggestions(types); // older API (404) or offline: same vocabulary, computed locally
    }
    setPool(next);
    setChecked((prev) => {
      const out = new Set(prev);
      const first = seenSuggested.current === null;
      for (const e of next.suggested) {
        const isNew = first ? !prefilled.current : !seenSuggested.current!.has(e.id);
        if (isNew) out.add(e.id);
      }
      seenSuggested.current = new Set(next.suggested.map((e) => e.id));
      return out;
    });
    setPoolLoading(false);
  }, []);

  const toggleType = (id: string) => setSelected((prev) => (prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]));

  const toggleElement = (id: string) =>
    setChecked((prev) => {
      const out = new Set(prev);
      if (out.has(id)) out.delete(id);
      else out.add(id);
      return out;
    });

  const addCustom = () => {
    const label = customText.trim();
    if (!label) return;
    const id = `custom-${slugify(label)}`;
    if (!slugify(label) || custom.some((c) => c.id === id) || (pool?.all ?? ELEMENTS).some((e) => e.id === id)) {
      toast('That one is already on the list.');
      return;
    }
    setCustom((prev) => [...prev, { id, label, furnitureIds: [], custom: true }]);
    setChecked((prev) => new Set(prev).add(id));
    setCustomText('');
  };

  const removeCustom = (id: string) => {
    setCustom((prev) => prev.filter((c) => c.id !== id));
    setChecked((prev) => {
      const out = new Set(prev);
      out.delete(id);
      return out;
    });
  };

  const goToStep2 = () => {
    setStep(2);
    void loadPool(selected);
  };

  const chosenElements = (): RoomElement[] => {
    const all = pool?.all ?? ELEMENTS;
    return [...all.filter((e) => checked.has(e.id)), ...custom.filter((e) => checked.has(e.id))];
  };

  const submit = async () => {
    setBusy(true);
    try {
      const elements = chosenElements();
      if (editMode && roomId) {
        await api.updateRoomSetup(roomId, { spaceTypes: selected, elements });
        toast('Setup saved');
        router.back();
        return;
      }
      if (!draft) return;
      const res = await api.createRoomFromDraft({ ...draft, name: name.trim() || draft.name }, { spaceTypes: selected, elements });
      setRoomDraft(null);
      router.replace(`/editor/${encodeURIComponent(res.currentLayout.id)}`);
    } catch (e) {
      toast(((e as Error | null)?.message ?? String(e)), { tone: 'danger', ms: 4500 });
    } finally {
      setBusy(false);
    }
  };

  const labelFor = (id: string) => spaceTypes.find((t) => t.id === id)?.label ?? id;

  // Suggested elements grouped by the space type that suggested them (first type wins), then the rest.
  const groups = useMemo(() => {
    if (!pool) return [];
    const placed = new Set<string>();
    const out: { key: string; title: string; items: RoomElement[] }[] = [];
    for (const st of selected) {
      const ids = SUGGESTIONS[st] ?? [];
      const items = pool.suggested.filter((e) => ids.includes(e.id) && !placed.has(e.id));
      items.forEach((e) => placed.add(e.id));
      if (items.length) out.push({ key: st, title: spaceTypes.find((t) => t.id === st)?.label ?? st, items });
    }
    const rest = pool.suggested.filter((e) => !placed.has(e.id));
    if (rest.length) out.push({ key: 'rest', title: 'Also suggested', items: rest });
    return out;
  }, [pool, selected, spaceTypes]);

  const more = useMemo(() => {
    if (!pool) return [];
    const suggestedIds = new Set(pool.suggested.map((e) => e.id));
    return pool.all.filter((e) => !suggestedIds.has(e.id));
  }, [pool]);

  const title = editMode ? 'Edit setup' : 'Set up room';
  const checkedCount = chosenElements().length;

  // ---- Guard states -------------------------------------------------------------------------
  if (!editMode && !draft) {
    return (
      <Screen>
        <Stack.Screen options={{ title }} />
        <View style={styles.content}>
          <Tile style={{ alignItems: 'center', gap: spacing.sm }}>
            <MaterialCommunityIcons name="cube-outline" size={40} color={colors.inkSoft} />
            <Text style={[type.h2, { textAlign: 'center' }]}>Nothing to set up yet</Text>
            <Text style={[type.small, { textAlign: 'center' }]}>Scan a room or enter its dimensions first, then come back here to say what the space is for.</Text>
            <Button label="Go home" icon="home-outline" onPress={() => router.replace('/')} style={{ marginTop: spacing.sm, alignSelf: 'stretch' }} />
          </Tile>
        </View>
      </Screen>
    );
  }
  if (editMode && roomState !== 'ready') {
    return (
      <Screen>
        <Stack.Screen options={{ title }} />
        <View style={styles.content}>
          <Tile>
            <EmptyNote>{roomState === 'loading' ? 'Loading room…' : 'Could not load this room.'}</EmptyNote>
          </Tile>
        </View>
      </Screen>
    );
  }

  const summaryName = editMode ? roomName : name.trim() || draft?.name;
  const hint =
    detectedCount > 0
      ? `RoomPlan found ${detectedCount} piece${detectedCount === 1 ? '' : 's'} — you can add them from the palette later`
      : editMode
        ? null
        : 'The room starts clean: walls, doors and windows only. You place the furniture.';

  return (
    <Screen>
      <Stack.Screen options={{ title }} />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Text style={styles.stepLabel}>Step {step} of 2</Text>
          <Text style={type.title}>{step === 1 ? 'What kind of space is this?' : 'What does this room need?'}</Text>
          <Text style={[type.subtitle, { marginTop: 2 }]}>
            {step === 1 ? 'Pick everything that applies — rooms often do more than one job.' : 'Untick what you do not need and add anything missing.'}
          </Text>

          <Tile style={styles.summary}>
            <View style={styles.summaryIcon}>
              <MaterialCommunityIcons name={draft?.source === 'manual' ? 'ruler-square' : 'cube-scan'} size={20} color={colors.tile} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.summaryName} numberOfLines={1}>
                {summaryName}
              </Text>
              <Text style={type.small} numberOfLines={1}>
                {roomDims ? `${formatDims(roomDims, units)} · ${formatArea(roomDims.l, roomDims.w, units)}` : 'Dimensions pending'}
              </Text>
              {hint ? <Text style={[type.small, { marginTop: 2 }]}>{hint}</Text> : null}
            </View>
          </Tile>

          {step === 1 ? (
            <>
              {!editMode ? (
                <Field label="Room name" value={name} onChangeText={setName} autoCapitalize="words" placeholder={draft?.name} style={{ backgroundColor: colors.tile }} />
              ) : null}
              <View style={styles.grid}>
                {spaceTypes.map((t) => {
                  const on = selected.includes(t.id);
                  return (
                    <Pressable
                      key={t.id}
                      onPress={() => toggleType(t.id)}
                      accessibilityRole="checkbox"
                      accessibilityState={{ checked: on }}
                      accessibilityLabel={t.label}
                      style={({ pressed }) => [styles.card, on && styles.cardOn, pressed && styles.pressed]}
                    >
                      <View style={[styles.cardIcon, on && styles.cardIconOn]}>
                        <MaterialCommunityIcons name={SPACE_TYPE_ICONS[t.id] ?? ('shape-outline' as IconName)} size={26} color={on ? colors.ink : colors.tile} />
                      </View>
                      <Text style={[styles.cardLabel, on && { color: colors.tile }]}>{t.label}</Text>
                      <MaterialCommunityIcons
                        name={on ? 'check-circle' : 'circle-outline'}
                        size={20}
                        color={on ? colors.tile : colors.tileMuted}
                        style={styles.cardCheck}
                      />
                    </Pressable>
                  );
                })}
              </View>
            </>
          ) : (
            <View style={{ gap: spacing.lg }}>
              {pool === null || poolLoading ? (
                <Tile>
                  <EmptyNote>Finding what a {selected.map(labelFor).join(' + ').toLowerCase() || 'room'} usually needs…</EmptyNote>
                </Tile>
              ) : (
                <>
                  {groups.length === 0 ? (
                    <Tile>
                      <EmptyNote>No suggestions for this mix — pick from “More” below or add your own.</EmptyNote>
                    </Tile>
                  ) : null}
                  {groups.map((g) => (
                    <Section key={g.key} title={g.title} tag={g.key === 'rest' ? undefined : 'suggested'}>
                      {g.items.map((e, i) => (
                        <ElementRow key={e.id} element={e} checked={checked.has(e.id)} first={i === 0} onToggle={() => toggleElement(e.id)} />
                      ))}
                    </Section>
                  ))}
                  {more.length ? (
                    <Section title="More">
                      {more.map((e, i) => (
                        <ElementRow key={e.id} element={e} checked={checked.has(e.id)} first={i === 0} onToggle={() => toggleElement(e.id)} />
                      ))}
                    </Section>
                  ) : null}
                  <Section title="Add your own">
                    {custom.map((e, i) => (
                      <ElementRow key={e.id} element={e} checked={checked.has(e.id)} first={i === 0} onToggle={() => toggleElement(e.id)} onRemove={() => removeCustom(e.id)} />
                    ))}
                    <View style={[styles.addRow, custom.length > 0 && styles.rowBorder]}>
                      <TextInput
                        value={customText}
                        onChangeText={setCustomText}
                        onSubmitEditing={addCustom}
                        placeholder="e.g. Piano, cat tree, easel"
                        placeholderTextColor="#A08B7C"
                        returnKeyType="done"
                        autoCapitalize="sentences"
                        style={styles.addInput}
                        accessibilityLabel="Add your own element"
                      />
                      <Pressable onPress={addCustom} disabled={!customText.trim()} accessibilityRole="button" accessibilityLabel="Add" style={({ pressed }) => [styles.addButton, !customText.trim() && { opacity: 0.4 }, pressed && styles.pressed]}>
                        <MaterialCommunityIcons name="plus" size={22} color={colors.tile} />
                      </Pressable>
                    </View>
                  </Section>
                </>
              )}
            </View>
          )}
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          {step === 1 ? (
            <Button
              label={selected.length ? `Continue with ${selected.length} selected` : 'Pick at least one'}
              icon="arrow-right"
              onPress={goToStep2}
              disabled={selected.length === 0}
            />
          ) : (
            <View style={{ flexDirection: 'row', gap: spacing.sm }}>
              <Button label="Back" icon="arrow-left" variant="ghost" onPress={() => setStep(1)} disabled={busy} style={{ flex: 1 }} />
              <Button
                label={editMode ? 'Save setup' : 'Create clean room'}
                icon={editMode ? 'content-save-outline' : 'home-plus-outline'}
                onPress={submit}
                busy={busy}
                disabled={poolLoading}
                style={{ flex: 2 }}
              />
            </View>
          )}
          {step === 2 ? (
            <Text style={[type.small, { textAlign: 'center', marginTop: spacing.sm }]}>
              {checkedCount} element{checkedCount === 1 ? '' : 's'} · {selected.map(labelFor).join(', ')}
            </Text>
          ) : null}
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

function Section({ title, tag, children }: { title: string; tag?: string; children: React.ReactNode }) {
  return (
    <View>
      <View style={styles.sectionRow}>
        <Text style={type.h2}>{title}</Text>
        {tag ? <Chip label={tag} tone="accent" /> : null}
      </View>
      <Tile style={{ padding: spacing.sm }}>{children}</Tile>
    </View>
  );
}

function ElementRow({
  element,
  checked,
  first,
  onToggle,
  onRemove,
}: {
  element: RoomElement;
  checked: boolean;
  first: boolean;
  onToggle: () => void;
  onRemove?: () => void;
}) {
  const sub = element.custom ? 'Your own' : element.zone ? `Clear floor zone · ${element.zone.w} × ${element.zone.d} m` : null;
  return (
    <Pressable
      onPress={onToggle}
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      accessibilityLabel={element.label}
      style={({ pressed }) => [styles.row, !first && styles.rowBorder, pressed && styles.pressed]}
    >
      <MaterialCommunityIcons name={checked ? 'checkbox-marked' : 'checkbox-blank-outline'} size={24} color={checked ? colors.ink : colors.inkSoft} />
      <View style={{ flex: 1 }}>
        <Text style={[styles.rowLabel, !checked && { color: colors.inkSoft }]}>{element.label}</Text>
        {sub ? <Text style={type.small}>{sub}</Text> : null}
      </View>
      {onRemove ? (
        <Pressable onPress={onRemove} hitSlop={8} accessibilityRole="button" accessibilityLabel={`Remove ${element.label}`}>
          <MaterialCommunityIcons name="close-circle-outline" size={22} color={colors.inkSoft} />
        </Pressable>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg, paddingBottom: spacing.xl },
  stepLabel: { ...type.small, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginBottom: spacing.xs },
  summary: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, padding: spacing.md, marginTop: spacing.lg, marginBottom: spacing.lg },
  summaryIcon: { width: 40, height: 40, borderRadius: radius.sm, backgroundColor: colors.accentDeep, alignItems: 'center', justifyContent: 'center' },
  summaryName: { fontSize: 15, fontWeight: '700', color: colors.ink },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  card: {
    flexGrow: 1,
    flexBasis: '45%',
    minHeight: 120,
    backgroundColor: colors.tile,
    borderRadius: radius.lg,
    padding: spacing.md,
    justifyContent: 'space-between',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  cardOn: { backgroundColor: colors.ink, borderColor: colors.ink },
  cardIcon: { width: 48, height: 48, borderRadius: radius.md, backgroundColor: colors.ink, alignItems: 'center', justifyContent: 'center' },
  cardIconOn: { backgroundColor: colors.tile },
  cardLabel: { fontSize: 16, fontWeight: '700', color: colors.ink, marginTop: spacing.sm },
  cardCheck: { position: 'absolute', top: spacing.md, right: spacing.md },
  pressed: { opacity: 0.75 },
  sectionRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, padding: spacing.sm, minHeight: 48, borderRadius: radius.sm },
  rowBorder: { borderTopWidth: 1, borderTopColor: colors.tileMuted },
  rowLabel: { fontSize: 15, fontWeight: '600', color: colors.ink },
  addRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, padding: spacing.sm },
  addInput: {
    flex: 1,
    backgroundColor: colors.white,
    borderRadius: radius.sm,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    color: colors.ink,
    borderWidth: 1,
    borderColor: colors.tileMuted,
  },
  addButton: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: colors.ink, alignItems: 'center', justifyContent: 'center' },
  footer: { paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.bg, borderTopWidth: 1, borderTopColor: colors.bgDeep },
});
