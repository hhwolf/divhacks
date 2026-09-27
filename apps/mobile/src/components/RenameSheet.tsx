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
  return (
    <Modal visible={visible} animationType="fade" transparent onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.backdrop}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Close" />
        <View style={styles.card}>
          <Text style={[type.h2, { marginBottom: spacing.md }]}>{title}</Text>
          <Field value={name} onChangeText={setName} autoFocus autoCapitalize="words" maxLength={60} placeholder="Room name" onSubmitEditing={() => clean && onSave(clean)} returnKeyType="done" />
          <View style={{ flexDirection: 'row', gap: spacing.sm }}>
            <Button label="Cancel" variant="ghost" onPress={onClose} style={{ flex: 1 }} />
            <Button label="Save" icon="check" onPress={() => onSave(clean)} busy={busy} disabled={!clean || clean === initial} style={{ flex: 1 }} />
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
