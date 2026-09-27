import React, { useState } from 'react';
import { KeyboardAvoidingView, Modal, Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, radius, spacing, type } from '../theme';
import type { Dimensions, Units } from '../types';
import { feetInchesToMeters, parseNum } from '../units';
import { Button, Chip, Field } from './ui';

interface Props {
  visible: boolean;
  units: Units;
  busy?: boolean;
  onClose: () => void;
  onSubmit: (dims: Dimensions, name: string) => void;
}

type Row = { ft: string; in: string; m: string };
const empty = (): Row => ({ ft: '', in: '', m: '' });

/** Sheet for "Enter dimensions": feet + inches by default, meters when units are metric. Emits meters. */
export function DimensionsSheet({ visible, units: initialUnits, busy, onClose, onSubmit }: Props) {
  const [units, setUnits] = useState<Units>(initialUnits);
  const [name, setName] = useState('My room');
  const [length, setLength] = useState<Row>(empty());
  const [width, setWidth] = useState<Row>(empty());
  const [height, setHeight] = useState<Row>({ ft: '8', in: '0', m: '2.7' });
  const [error, setError] = useState<string | null>(null);

  React.useEffect(() => setUnits(initialUnits), [initialUnits, visible]);

  const toMeters = (r: Row): number => {
    if (units === 'metric') return parseNum(r.m);
    const ft = r.ft.trim() === '' ? 0 : parseNum(r.ft);
    const inch = r.in.trim() === '' ? 0 : parseNum(r.in);
    if (r.ft.trim() === '' && r.in.trim() === '') return NaN;
    return feetInchesToMeters(ft, inch);
  };

  const submit = () => {
    const l = toMeters(length);
    const w = toMeters(width);
    const h = toMeters(height);
    if (![l, w, h].every((v) => Number.isFinite(v) && v > 0)) {
      setError('Please fill in length, width and height with positive numbers.');
      return;
    }
    if (l > 30 || w > 30 || h > 6) {
      setError('Those look too large for a room. Double-check the units.');
      return;
    }
    setError(null);
    onSubmit({ l: round(l), w: round(w), h: round(h) }, name.trim() || 'My room');
  };

  const renderRow = (label: string, row: Row, set: (r: Row) => void) =>
    units === 'metric' ? (
      <Field
        label={`${label} (m)`}
        keyboardType="decimal-pad"
        value={row.m}
        onChangeText={(m) => set({ ...row, m })}
        placeholder="3.4"
      />
    ) : (
      <View style={{ flexDirection: 'row', gap: spacing.sm }}>
        <View style={{ flex: 1 }}>
          <Field label={`${label} (ft)`} keyboardType="number-pad" value={row.ft} onChangeText={(ft) => set({ ...row, ft })} placeholder="11" />
        </View>
        <View style={{ flex: 1 }}>
          <Field label="in" keyboardType="number-pad" value={row.in} onChangeText={(v) => set({ ...row, in: v })} placeholder="2" />
        </View>
      </View>
    );

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.backdrop}>
        <Pressable style={{ flex: 1 }} onPress={onClose} accessibilityLabel="Close" />
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <View style={styles.headerRow}>
            <Text style={type.h2}>Enter dimensions</Text>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <Chip label="ft / in" tone={units === 'imperial' ? 'ink' : 'tile'} onPress={() => setUnits('imperial')} />
              <Chip label="metric" tone={units === 'metric' ? 'ink' : 'tile'} onPress={() => setUnits('metric')} />
            </View>
          </View>
          <Field label="Room name" value={name} onChangeText={setName} autoCapitalize="words" placeholder="My room" />
          {renderRow('Length', length, setLength)}
          {renderRow('Width', width, setWidth)}
          {renderRow('Ceiling height', height, setHeight)}
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm }}>
            <Button label="Cancel" variant="ghost" onPress={onClose} style={{ flex: 1 }} />
            <Button label="Create room" onPress={submit} busy={busy} style={{ flex: 2 }} icon="home-plus" />
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const round = (v: number) => Math.round(v * 100) / 100;

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(37,52,32,0.4)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: colors.tile,
    borderTopLeftRadius: radius.lg + 4,
    borderTopRightRadius: radius.lg + 4,
    padding: spacing.lg,
    paddingBottom: spacing.xl + 12,
  },
  handle: { alignSelf: 'center', width: 44, height: 5, borderRadius: 3, backgroundColor: colors.tileMuted, marginBottom: spacing.md },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.md },
  error: { color: colors.danger, fontSize: 13, marginBottom: spacing.sm },
});
