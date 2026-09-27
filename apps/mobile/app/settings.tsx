import { MaterialCommunityIcons } from '@expo/vector-icons';
import Constants from 'expo-constants';
import { useRouter } from 'expo-router';
import React, { useCallback, useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Account } from '../src/components/Account';
import { api } from '../src/api';
import { useToast } from '../src/components/Toast';
import { Button, Chip, Field, Screen, SectionTitle, Tile } from '../src/components/ui';
import { DEFAULT_API_URL, DEFAULT_WEB_URL, useStore } from '../src/store';
import { colors, spacing, type } from '../src/theme';
import type { HealthResponse } from '../src/types';

export default function Settings() {
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const { units, apiUrl, webUrl, setUnits, setUrls, resetUrls, setOnboarded } = useStore();
  const router = useRouter();

  const [apiDraft, setApiDraft] = useState(apiUrl);
  const [webDraft, setWebDraft] = useState(webUrl);
  const [health, setHealth] = useState<HealthResponse | null | 'down'>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => setApiDraft(apiUrl), [apiUrl]);
  useEffect(() => setWebDraft(webUrl), [webUrl]);

  const check = useCallback(async () => {
    setChecking(true);
    try {
      setHealth(await api.health());
    } catch {
      setHealth('down');
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check, apiUrl]);

  const dirty = apiDraft.trim().replace(/\/+$/, '') !== apiUrl || webDraft.trim().replace(/\/+$/, '') !== webUrl;

  const save = () => {
    setUrls({ apiUrl: apiDraft, webUrl: webDraft });
    toast('Saved. The next request uses the new URLs.');
  };

  return (
    <Screen>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + spacing.xl }]} keyboardShouldPersistTaps="handled">
          <SectionTitle>Account</SectionTitle><Account />
          <SectionTitle>Units</SectionTitle>
          <Tile style={{ flexDirection: 'row', gap: spacing.sm, alignItems: 'center' }}>
            <Chip icon="ruler" label="Feet & inches" tone={units === 'imperial' ? 'ink' : 'tile'} onPress={() => setUnits('imperial')} style={styles.chipOutline} />
            <Chip icon="ruler-square" label="Metric" tone={units === 'metric' ? 'ink' : 'tile'} onPress={() => setUnits('metric')} style={styles.chipOutline} />
          </Tile>

          <SectionTitle>Servers</SectionTitle>
          <Tile>
            <Field label="API URL" value={apiDraft} onChangeText={setApiDraft} keyboardType="url" placeholder={DEFAULT_API_URL} />
            <Field label="Editor URL" value={webDraft} onChangeText={setWebDraft} keyboardType="url" placeholder={DEFAULT_WEB_URL} />
            <View style={{ flexDirection: 'row', gap: spacing.sm }}>
              <Button label="Reset" variant="ghost" onPress={() => { resetUrls(); toast('Reset'); }} style={{ flex: 1 }} />
              <Button label="Save" icon="content-save-outline" onPress={save} disabled={!dirty} style={{ flex: 1 }} />
            </View>
          </Tile>

          <SectionTitle
            right={<Chip icon="refresh" label={checking ? 'Checking…' : 'Recheck'} onPress={checking ? undefined : check} style={styles.chipOutline} />}
          >
            Health
          </SectionTitle>
          <Tile>
            {health === null ? (
              <Text style={type.body}>Checking…</Text>
            ) : health === 'down' ? (
              <View style={styles.row}>
                <MaterialCommunityIcons name="cloud-off-outline" size={20} color={colors.danger} />
                <Text style={[type.body, { color: colors.danger, flex: 1 }]}>Server unreachable</Text>
              </View>
            ) : (
              <>
                <View style={[styles.row, { marginBottom: spacing.sm }]}>
                  <Chip label={health.mode} tone={health.mode === 'live' ? 'accent' : 'tile'} style={styles.chipOutline} />
                </View>
                {Object.entries(health.integrations ?? {}).map(([name, state]) => {
                  const live = state === 'live' || state === true;
                  return (
                    <View key={name} style={styles.row}>
                      <MaterialCommunityIcons name={live ? 'check-circle' : 'flask-outline'} size={18} color={live ? colors.accentDeep : colors.inkSoft} />
                      <Text style={[type.body, { flex: 1 }]}>{name}</Text>
                      <Text style={type.small}>{typeof state === 'boolean' ? (state ? 'live' : 'mock') : String(state)}</Text>
                    </View>
                  );
                })}
              </>
            )}
          </Tile>

          <SectionTitle>About</SectionTitle>
          <Tile>
            <Button label="Show intro" icon="play-circle-outline" variant="ghost" onPress={() => { setOnboarded(false); router.replace('/welcome'); }} />
            <Text style={[type.small, { marginTop: spacing.md, textAlign: 'center' }]}>v{Constants.expoConfig?.version ?? '1.0.0'}</Text>
          </Tile>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg, gap: spacing.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: 4 },
  chipOutline: { borderWidth: 1, borderColor: colors.tileMuted },
});
