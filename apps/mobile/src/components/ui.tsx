import { MaterialCommunityIcons } from '@expo/vector-icons';
import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
  type StyleProp,
} from 'react-native';

import { colors, radius, shadow, spacing, type } from '../theme';

export type IconName = React.ComponentProps<typeof MaterialCommunityIcons>['name'];

export function Screen({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.screen, style]}>{children}</View>;
}

export function Tile({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.tile, style]}>{children}</View>;
}

export function BigCard({
  icon,
  title,
  subtitle,
  onPress,
  busy,
  disabled,
}: {
  icon: IconName;
  title: string;
  subtitle: string;
  onPress: () => void;
  busy?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={busy || disabled}
      style={({ pressed }) => [styles.bigCard, pressed && styles.pressed, disabled && { opacity: 0.6 }]}
      accessibilityRole="button"
      accessibilityLabel={title}
    >
      <View style={styles.bigIcon}>
        {busy ? <ActivityIndicator color={colors.tile} /> : <MaterialCommunityIcons name={icon} size={30} color={colors.tile} />}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.bigTitle}>{title}</Text>
        <Text style={type.small}>{subtitle}</Text>
      </View>
      <MaterialCommunityIcons name="chevron-right" size={26} color={colors.inkSoft} />
    </Pressable>
  );
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  icon,
  busy,
  disabled,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  icon?: IconName;
  busy?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
}) {
  // Same pair as the welcome screen: solid forest primary, white with a forest outline for the rest.
  const bg = variant === 'primary' ? colors.forest : variant === 'danger' ? colors.danger : colors.white;
  const fg = variant === 'primary' || variant === 'danger' ? colors.white : colors.forest;
  return (
    <Pressable
      onPress={onPress}
      disabled={busy || disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: bg },
        (variant === 'secondary' || variant === 'ghost') && { borderWidth: 1.5, borderColor: colors.forest },
        pressed && styles.pressed,
        (busy || disabled) && { opacity: 0.55 },
        style,
      ]}
    >
      {busy ? (
        <ActivityIndicator color={fg} />
      ) : (
        <>
          {icon ? <MaterialCommunityIcons name={icon} size={18} color={fg} style={{ marginRight: 6 }} /> : null}
          <Text style={[styles.buttonLabel, { color: fg }]}>{label}</Text>
        </>
      )}
    </Pressable>
  );
}

export function Chip({
  label,
  icon,
  onPress,
  tone = 'tile',
  style,
}: {
  label: string;
  icon?: IconName;
  onPress?: () => void;
  tone?: 'tile' | 'ink' | 'accent' | 'danger' | 'warn';
  style?: ViewStyle;
}) {
  const bg =
    tone === 'ink' ? colors.forest : tone === 'accent' ? colors.sageTint : tone === 'danger' ? colors.danger : tone === 'warn' ? colors.warn : colors.tile;
  const fg = tone === 'ink' || tone === 'danger' ? colors.white : colors.forest;
  const inner = (
    <>
      {icon ? <MaterialCommunityIcons name={icon} size={14} color={fg} style={{ marginRight: 4 }} /> : null}
      <Text style={{ color: fg, fontSize: 13, fontWeight: '600' }}>{label}</Text>
    </>
  );
  if (!onPress) return <View style={[styles.chip, { backgroundColor: bg }, style]}>{inner}</View>;
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label} style={({ pressed }) => [styles.chip, { backgroundColor: bg, minHeight: 44, justifyContent: 'center' }, pressed && styles.pressed, style]}>
      {inner}
    </Pressable>
  );
}

export function Field(props: TextInputProps & { label?: string }) {
  const { label, style, ...rest } = props;
  return (
    <View style={{ marginBottom: spacing.md }}>
      {label ? <Text style={styles.fieldLabel}>{label}</Text> : null}
      <TextInput
        placeholderTextColor="#9AA392"
        autoCapitalize="none"
        autoCorrect={false}
        accessibilityLabel={label}
        {...rest}
        style={[styles.input, style]}
      />
    </View>
  );
}

export function SectionTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <View style={styles.sectionRow}>
      <Text style={type.h2}>{children}</Text>
      {right}
    </View>
  );
}

export function EmptyNote({ children }: { children: React.ReactNode }) {
  return <Text style={[type.small, { textAlign: 'center', paddingVertical: spacing.lg }]}>{children}</Text>;
}

export function IconButton({ icon, onPress, label, style }: { icon: IconName; onPress: () => void; label: string; style?: ViewStyle }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      hitSlop={8}
      style={({ pressed }) => [styles.iconButton, pressed && styles.pressed, style]}
    >
      <MaterialCommunityIcons name={icon} size={22} color={colors.tile} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  tile: { backgroundColor: colors.tile, borderRadius: radius.lg, padding: spacing.lg, ...shadow.soft },
  bigCard: {
    backgroundColor: colors.tile,
    borderRadius: radius.lg,
    padding: spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    ...shadow.soft,
  },
  bigIcon: { width: 56, height: 56, borderRadius: radius.md, backgroundColor: colors.forest, alignItems: 'center', justifyContent: 'center' },
  bigTitle: { fontSize: 18, fontWeight: '700', color: colors.ink, marginBottom: 2 },
  pressed: { opacity: 0.85, transform: [{ scale: 0.99 }] },
  button: {
    minHeight: 52,
    paddingVertical: 12,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md + 2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonLabel: { fontSize: 16, fontWeight: '700', flexShrink: 1, textAlign: 'center' },
  chip: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill },
  fieldLabel: { ...type.small, fontWeight: '600', marginBottom: 4 },
  input: {
    backgroundColor: colors.white,
    borderRadius: radius.sm,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    color: colors.ink,
    borderWidth: 1,
    borderColor: colors.tileMuted,
  },
  sectionRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.sm },
  iconButton: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: colors.forest, alignItems: 'center', justifyContent: 'center' },
});
