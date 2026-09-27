import { MaterialCommunityIcons } from '@expo/vector-icons';
import { Stack, useRouter } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '../src/api';
import { useToast } from '../src/components/Toast';
import { Button, EmptyNote, Field, Screen } from '../src/components/ui';
import { ELEMENTS, furnitureFor, SPACE_TYPES, suggestedElements, typeLabel } from '../src/spaces';
import { useStore } from '../src/store';
import { colors, radius, spacing, type } from '../src/theme';
import { formatArea, formatDims } from '../src/units';

const STEPS = ['Space', 'Needs', 'Review'] as const;

/**
 * After a scan (or typed dimensions): what kind of space is this (multi-select) → which elements it needs (suggested +
 * custom) → name + review. Creates the clean base room (walls/doors/windows/dimensions exactly as scanned, no furniture
 * unless the user opts in) and opens it so they can place what they own and build the Current Room.
 */
export default function Setup() {
  const router = useRouter();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const { pendingSetup, setPendingSetup, units } = useStore();
  const [step, setStep] = useState(0);
  const [types, setTypes] = useState<string[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [custom, setCustom] = useState<string[]>([]);
  const [draft, setDraft] = useState('');
  const [keepDetected, setKeepDetected] = useState(false);
  const [name, setName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const suggestions = useMemo(() => suggestedElements(types), [types]);
  const detected = pendingSetup?.kind === 'scan' ? pendingSetup.scan.objects.length : 0;
  const skeleton = pendingSetup?.kind === 'scan' ? pendingSetup.scan.skeleton : null;
  const dims = pendingSetup?.kind === 'scan' ? pendingSetup.scan.skeleton.dimensions : pendingSetup?.dims;
  const defaultName = types.length ? types.map(typeLabel).join(' + ') : pendingSetup?.kind === 'manual' ? pendingSetup.name : 'Scanned room';
  const roomName = (name ?? defaultName).trim() || defaultName;

  if (!pendingSetup || !dims) {
    return (
      <Screen style={{ justifyContent: 'center', padding: spacing.xl }}>
        <EmptyNote>No scan to set up. Start from Home.</EmptyNote>
        <Button label="Back to Home" onPress={() => router.replace('/')} />
      </Screen>
    );
  }

  const toggle = (list: string[], set: (v: string[]) => void, key: string) => set(list.includes(key) ? list.filter((k) => k !== key) : [...list, key]);
  const addCustom = () => {
    const label = draft.trim(); if (!label) return;
    if (!custom.some((c) => c.toLowerCase() === label.toLowerCase())) setCustom([...custom, label]);
    setDraft('');
  };

  const create = async () => {
    setBusy(true);
    try {
      const elementLabels = [...picked.map((k) => ELEMENTS[k]?.label ?? k), ...custom];
      const profile = { spaceTypes: types.map(typeLabel), elements: elementLabels, suggestedFurniture: furnitureFor(picked, custom) };
      const res = pendingSetup.kind === 'scan'
        ? await api.createScannedRoom(pendingSetup.scan, roomName, profile, keepDetected ? pendingSetup.scan.objects : [])
        : await api.createManualRoomWithProfile(pendingSetup.dims, roomName, profile);
      setPendingSetup(null);
      router.replace(`/editor/${encodeURIComponent(res.currentLayout.id)}`);
    } catch (e) {
      toast((e as Error).message, { tone: 'danger', ms: 4500 });
    } finally {
      setBusy(false);
    }
  };

  const canNext = step === 0 ? types.length > 0 : true;
  const next = () => (step < STEPS.length - 1 ? setStep(step + 1) : void create());

  return (
    <Screen>
      <Stack.Screen options={{ title: 'Set up your room' }} />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <View style={styles.progress}>
          {STEPS.map((s, i) => (
            <View key={s} style={styles.progressItem}>
              <View style={[styles.progressBar, i <= step && { backgroundColor: colors.forest }]} />
              <Text style={[styles.progressLabel, i === step && { color: colors.forest }]}>{s}</Text>
            </View>
          ))}
        </View>

        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {step === 0 ? (
            <>
              <Text style={type.eyebrow}>Step 1 of 3</Text>
              <Text style={styles.q}>What kind of space is this?</Text>
              <Text style={type.subtitle}>Pick all that apply.</Text>
              <View style={styles.grid}>
                {SPACE_TYPES.map((t) => {
                  const on = types.includes(t.key);
                  return (
                    <Pressable key={t.key} onPress={() => toggle(types, setTypes, t.key)} accessibilityLabel={t.label} accessibilityRole="checkbox" accessibilityState={{ checked: on }} style={({ pressed }) => [styles.typeCard, on && styles.typeOn, pressed && styles.pressed]}>
                      <View style={styles.typeTop}>
                        <MaterialCommunityIcons name={t.icon} size={26} color={on ? colors.white : colors.forest} />
                        <MaterialCommunityIcons name={on ? 'check-circle' : 'checkbox-blank-circle-outline'} size={20} color={on ? colors.white : colors.tileMuted} />
                      </View>
                      <Text style={[styles.typeLabel, on && { color: colors.white }]}>{t.label}</Text>
                      <Text style={[styles.typeBlurb, on && { color: 'rgba(255,255,255,0.75)' }]}>{t.blurb}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </>
          ) : step === 1 ? (
            <>
              <Text style={type.eyebrow}>Step 2 of 3</Text>
              <Text style={styles.q}>What should it make room for?</Text>
              <Text style={type.subtitle}>Pick what you want.</Text>
              <View style={styles.chips}>
                {suggestions.map((k) => {
                  const e = ELEMENTS[k]; const on = picked.includes(k);
                  return (
                    <Pressable key={k} onPress={() => toggle(picked, setPicked, k)} accessibilityLabel={e.label} accessibilityRole="checkbox" accessibilityState={{ checked: on }} style={({ pressed }) => [styles.el, on && styles.elOn, pressed && styles.pressed]}>
                      <MaterialCommunityIcons name={e.icon} size={18} color={on ? colors.white : colors.forest} />
                      <Text style={[styles.elText, on && { color: colors.white }]}>{e.label}</Text>
                      {on ? <MaterialCommunityIcons name="check" size={16} color={colors.white} /> : null}
                    </Pressable>
                  );
                })}
                {custom.map((c) => (
                  <Pressable key={`c-${c}`} onPress={() => setCustom(custom.filter((x) => x !== c))} accessibilityLabel={`Remove ${c}`} style={({ pressed }) => [styles.el, styles.elOn, pressed && styles.pressed]}>
                    <MaterialCommunityIcons name="star-four-points-outline" size={18} color={colors.white} />
                    <Text style={[styles.elText, { color: colors.white }]}>{c}</Text>
                    <MaterialCommunityIcons name="close" size={16} color={colors.white} />
                  </Pressable>
                ))}
              </View>
              <Text style={[type.small, { marginTop: spacing.lg, marginBottom: spacing.sm, fontWeight: '600' }]}>Something else?</Text>
              <View style={styles.addRow}>
                <TextInput value={draft} onChangeText={setDraft} placeholder="e.g. Keyboard stand, drying rack" placeholderTextColor="#9AA392" style={styles.addInput} onSubmitEditing={addCustom} returnKeyType="done" maxLength={40} />
                <Button label="Add" icon="plus" onPress={addCustom} disabled={!draft.trim()} />
              </View>
            </>
          ) : (
            <>
              <Text style={type.eyebrow}>Step 3 of 3</Text>
              <Text style={styles.q}>Name it and build the base</Text>
              <Field label="Room name" value={name ?? defaultName} onChangeText={setName} autoCapitalize="words" maxLength={60} />
              <View style={styles.summary}>
                <SummaryRow icon="floor-plan" label="Size" value={`${formatDims(dims, units)} · ${formatArea(dims.l, dims.w, units)}`} />
                {skeleton ? <SummaryRow icon="door" label="Openings" value={`${skeleton.doors.length} door${skeleton.doors.length === 1 ? '' : 's'} · ${skeleton.windows.length} window${skeleton.windows.length === 1 ? '' : 's'} · ${skeleton.walls.length} walls`} /> : <SummaryRow icon="door" label="Openings" value="None yet (typed dimensions)" />}
                <SummaryRow icon="home-variant-outline" label="Space" value={types.map(typeLabel).join(', ')} />
                <SummaryRow icon="checkbox-multiple-marked-outline" label="Needs" value={[...picked.map((k) => ELEMENTS[k].label), ...custom].join(', ') || 'Nothing picked'} />
                <View style={styles.note}>
                  <MaterialCommunityIcons name="shield-check-outline" size={18} color={colors.forest} />
                  <Text style={[type.small, { flex: 1, color: colors.forest }]}>Walls, doors and windows stay exactly as scanned.</Text>
                </View>
              </View>
              {detected > 0 ? (
                <View style={styles.switchRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>Add the {detected} detected item{detected === 1 ? '' : 's'}</Text>
                  </View>
                  <Switch value={keepDetected} onValueChange={setKeepDetected} trackColor={{ true: colors.accentDeep, false: colors.tileMuted }} thumbColor={colors.white} />
                </View>
              ) : null}
            </>
          )}
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          {step > 0 ? <Button label="Back" variant="ghost" onPress={() => setStep(step - 1)} style={{ flex: 1 }} /> : null}
          <Button label={step === STEPS.length - 1 ? 'Create base room' : 'Continue'} icon={step === STEPS.length - 1 ? 'cube-outline' : 'arrow-right'} onPress={next} disabled={!canNext} busy={busy} style={{ flex: 2 }} />
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

function SummaryRow({ icon, label, value }: { icon: React.ComponentProps<typeof MaterialCommunityIcons>['name']; label: string; value: string }) {
  return (
    <View style={styles.sumRow}>
      <MaterialCommunityIcons name={icon} size={18} color={colors.accentDeep} />
      <Text style={styles.sumLabel}>{label}</Text>
      <Text style={styles.sumValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  progress: { flexDirection: 'row', gap: spacing.sm, paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  progressItem: { flex: 1, gap: 6 },
  progressBar: { height: 4, borderRadius: 2, backgroundColor: colors.tileMuted },
  progressLabel: { fontSize: 12, fontWeight: '600', color: colors.inkSoft },
  content: { padding: spacing.lg, paddingBottom: spacing.xl * 2 },
  q: { fontSize: 24, fontWeight: '700', color: colors.ink, letterSpacing: -0.4, marginTop: 6, marginBottom: 6 },
  pressed: { opacity: 0.85, transform: [{ scale: 0.99 }] },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, marginTop: spacing.lg },
  typeCard: { width: '47.5%', backgroundColor: colors.tile, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.tileMuted, gap: 4 },
  typeOn: { backgroundColor: colors.forest, borderColor: colors.forest },
  typeTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: spacing.sm },
  typeLabel: { fontSize: 16, fontWeight: '700', color: colors.ink },
  typeBlurb: { fontSize: 12, color: colors.inkSoft },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.lg },
  el: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, backgroundColor: colors.tile, borderWidth: 1, borderColor: colors.tileMuted },
  elOn: { backgroundColor: colors.accentDeep, borderColor: colors.accentDeep },
  elText: { fontSize: 14, fontWeight: '600', color: colors.ink },
  addRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'center' },
  addInput: { flex: 1, backgroundColor: colors.white, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 12, fontSize: 15, color: colors.ink, borderWidth: 1, borderColor: colors.tileMuted },
  summary: { backgroundColor: colors.tile, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.tileMuted, gap: spacing.md },
  sumRow: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm },
  sumLabel: { width: 72, fontSize: 13, fontWeight: '700', color: colors.inkSoft },
  sumValue: { flex: 1, fontSize: 14, color: colors.ink },
  note: { flexDirection: 'row', gap: spacing.sm, backgroundColor: colors.sageTint, borderRadius: radius.sm, padding: spacing.md, alignItems: 'center' },
  switchRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, backgroundColor: colors.tile, borderRadius: radius.lg, padding: spacing.lg, marginTop: spacing.md, borderWidth: 1, borderColor: colors.tileMuted },
  rowTitle: { fontSize: 15, fontWeight: '700', color: colors.ink, marginBottom: 2 },
  footer: { flexDirection: 'row', gap: spacing.sm, paddingHorizontal: spacing.lg, paddingTop: spacing.md, backgroundColor: colors.bg, borderTopWidth: 1, borderTopColor: colors.tileMuted },
});
