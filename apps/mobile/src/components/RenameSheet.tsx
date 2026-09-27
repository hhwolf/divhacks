import React, { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Modal, Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, radius, spacing, type } from '../theme';
import { Button, Field } from './ui';

/** Cross-platform rename sheet (Alert.prompt is iOS-only). */
export function RenameSheet({ visible, title, initial, busy, onClose, onSave }: {
  visible: boolean; title: string; initial: string; busy?: boolean; onClose: () => void; onSave: (name: string) => void;
}) {
  const [name, setName] = useState(initial);
  useEffect(() => { if (visible) setName(initial); }, [visible, initial]);
  const clean = name.trim();
  const save = () => { if (!busy && clean && clean !== initial) onSave(clean); };
  const close = () => { if (!busy) onClose(); };
  return (
    <Modal visible={visible} animationType="fade" transparent onRequestClose={close}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.backdrop}>
        <Pressable style={StyleSheet.absoluteFill} onPress={close} accessibilityLabel="Close" />
        <View style={styles.card}>
          <Text style={[type.h2, { marginBottom: spacing.md }]}>{title}</Text>
          <Field value={name} onChangeText={setName} editable={!busy} autoFocus autoCapitalize="words" maxLength={60} placeholder="Room name" onSubmitEditing={save} returnKeyType="done" />
          <View style={{ flexDirection: 'row', gap: spacing.sm }}>
            <Button label="Cancel" variant="ghost" onPress={close} disabled={busy} style={{ flex: 1 }} />
            <Button label="Save" icon="check" onPress={save} busy={busy} disabled={!clean || clean === initial} style={{ flex: 1 }} />
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(37,52,32,0.4)', justifyContent: 'center', padding: spacing.xl },
  card: { backgroundColor: colors.tile, borderRadius: radius.lg, padding: spacing.lg },
});
