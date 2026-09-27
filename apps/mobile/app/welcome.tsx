import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import React, { useRef, useState } from 'react';
import { ActivityIndicator, NativeScrollEvent, NativeSyntheticEvent, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '../src/api';
import { useToast } from '../src/components/Toast';
import { useStore } from '../src/store';
import { colors, radius, spacing } from '../src/theme';

type Icon = React.ComponentProps<typeof MaterialCommunityIcons>['name'];
interface Slide { key: string; title: string; body: string; Art: () => React.ReactElement }

const SLIDES: Slide[] = [
  { key: 'scan', title: 'Scan your room once', body: 'Walls, doors and windows in one pass.', Art: ScanArt },
  { key: 'current', title: 'Build your Current Room', body: 'Place what you own. Lock what never moves.', Art: CurrentArt },
  { key: 'ask', title: 'Ask for new layouts', body: 'Every answer is a new variant.', Art: AskArt },
];

/** First-launch intro: tinted art area with floating app-preview cards, title, body, page dots, primary + outline actions. */
export default function Welcome() {
  const router = useRouter();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();
  const setOnboarded = useStore((s) => s.setOnboarded);
  const scroller = useRef<ScrollView>(null);
  const [index, setIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const last = index === SLIDES.length - 1;
  const artH = Math.min(440, Math.max(300, height * 0.5));

  const go = (i: number) => { scroller.current?.scrollTo({ x: i * width, animated: true }); setIndex(i); };
  const onScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const i = Math.round(e.nativeEvent.contentOffset.x / Math.max(1, width));
    if (i !== index && i >= 0 && i < SLIDES.length) setIndex(i);
  };
  const finish = () => { setOnboarded(true); router.replace('/'); };
  const trySample = async () => {
    setBusy(true);
    try {
      const res = await api.createSampleRoom('l-shaped');
      setOnboarded(true);
      router.replace('/');
      router.push(`/editor/${encodeURIComponent(res.currentLayout.id)}`);
    } catch (e) {
      toast((e as Error).message, { tone: 'danger', ms: 4500 });
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.root}>
      <ScrollView ref={scroller} horizontal pagingEnabled showsHorizontalScrollIndicator={false} onScroll={onScroll} scrollEventThrottle={32} style={{ flex: 1 }}>
        {SLIDES.map(({ key, title, body, Art }) => (
          <View key={key} style={{ width }}>
            <LinearGradient colors={[colors.sageTint, '#EAF0E2', colors.bg]} locations={[0, 0.6, 1]} style={[styles.art, { height: artH + insets.top, paddingTop: insets.top + spacing.lg }]}>
              <Art />
            </LinearGradient>
            <View style={styles.copy}>
              <Text style={styles.title}>{title}</Text>
              <Text style={styles.body}>{body}</Text>
            </View>
          </View>
        ))}
      </ScrollView>

      <View style={[styles.bottom, { paddingBottom: insets.bottom + spacing.lg }]}>
        <View style={styles.dots}>
          {SLIDES.map((s, i) => (
            <Pressable key={s.key} onPress={() => go(i)} accessibilityLabel={`Slide ${i + 1}`} hitSlop={8}>
              <View style={[styles.dot, i === index && styles.dotOn]} />
            </Pressable>
          ))}
        </View>
        <Pressable onPress={last ? finish : () => go(index + 1)} accessibilityRole="button" accessibilityLabel={last ? 'Get started' : 'Next'} style={({ pressed }) => [styles.primary, pressed && styles.pressed]}>
          <Text style={styles.primaryText}>{last ? 'Get started' : 'Next'}</Text>
        </Pressable>
        <Pressable onPress={last ? trySample : finish} disabled={busy} accessibilityRole="button" accessibilityLabel={last ? 'Try the sample room' : 'Skip'} style={({ pressed }) => [styles.secondary, pressed && styles.pressed]}>
          {busy ? <ActivityIndicator color={colors.forest} /> : <Text style={styles.secondaryText}>{last ? 'Try the sample room' : 'Skip'}</Text>}
        </Pressable>
      </View>
    </View>
  );
}

// ---- floating preview cards ------------------------------------------------------------------------------------

const tilt = (z: number) => ({ transform: [{ perspective: 900 }, { rotateX: '14deg' }, { rotateZ: `${z}deg` }] });

function Card({ children, style }: { children: React.ReactNode; style?: object }) {
  return <View style={[styles.card, style]}>{children}</View>;
}
function CardHead({ icon, title, sub }: { icon: Icon; title: string; sub: string }) {
  return (
    <View style={styles.cardHead}>
      <View style={styles.cardIcon}><MaterialCommunityIcons name={icon} size={14} color={colors.white} /></View>
      <View style={{ flex: 1 }}>
        <Text style={styles.cardTitle}>{title}</Text>
        <Text style={styles.cardSub}>{sub}</Text>
      </View>
    </View>
  );
}
function Row({ icon, label, tag, on }: { icon: Icon; label: string; tag: string; on?: boolean }) {
  return (
    <View style={styles.row}>
      <MaterialCommunityIcons name={icon} size={15} color={colors.forest} />
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={[styles.tag, on && { backgroundColor: colors.forest }]}><Text style={[styles.tagText, on && { color: colors.white }]}>{tag}</Text></View>
    </View>
  );
}

function ScanArt() {
  return (
    <View style={styles.stage}>
      <Card style={[styles.back, tilt(-7)]}>
        <CardHead icon="cube-scan" title="Scanning room" sub="Walk slowly along the walls" />
        <Row icon="wall" label="Walls" tag="4" on />
        <Row icon="door" label="Doors" tag="1" on />
        <Row icon="window-closed-variant" label="Windows" tag="1" on />
        <View style={styles.progress}><View style={[styles.progressFill, { width: '82%' }]} /></View>
      </Card>
      <Card style={[styles.front, tilt(-7)]}>
        <CardHead icon="floor-plan" title="Clean base room" sub="11' 10&quot; × 10' 6&quot; · 124 sq ft" />
        <View style={styles.plan}>
          <View style={styles.planWindow} />
          <View style={styles.planDoor} />
          <Text style={styles.planDim}>11' 10"</Text>
        </View>
      </Card>
    </View>
  );
}

function CurrentArt() {
  const bars = [0.45, 0.62, 0.55, 0.8, 0.7];
  return (
    <View style={styles.stage}>
      <Card style={[styles.back, tilt(-7)]}>
        <CardHead icon="lock-outline" title="Current Room" sub="Only you can change it" />
        <Row icon="bed-outline" label="Double bed" tag="Locked" on />
        <Row icon="desk" label="Oak desk" tag="Placed" />
        <Row icon="dresser-outline" label="Dresser" tag="Placed" />
      </Card>
      <Card style={[styles.front, tilt(-7)]}>
        <CardHead icon="chart-bar" title="Open floor" sub="62% · walkability Good" />
        <View style={styles.bars}>
          {bars.map((h, i) => <View key={i} style={[styles.bar, { height: 64 * h }, i === 3 && { backgroundColor: colors.forest }]} />)}
        </View>
      </Card>
    </View>
  );
}

function AskArt() {
  return (
    <View style={styles.stage}>
      <Card style={[styles.back, tilt(-7)]}>
        <CardHead icon="message-text-outline" title="You" sub="via iMessage" />
        <View style={styles.bubble}><Text style={styles.bubbleText}>Will this desk fit beside my window without moving my bed?</Text></View>
      </Card>
      <Card style={[styles.front, tilt(-7)]}>
        <CardHead icon="leaf" title="Marketplace Desk" sub="New variant · 2 in to spare" />
        <View style={styles.chips}>
          <View style={styles.chip}><MaterialCommunityIcons name="lock-outline" size={11} color={colors.forest} /><Text style={styles.chipText}>Current Room</Text></View>
          <View style={[styles.chip, { backgroundColor: colors.forest }]}><Text style={[styles.chipText, { color: colors.white }]}>Marketplace Desk</Text></View>
        </View>
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  art: { alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing.lg },
  copy: { paddingHorizontal: spacing.xl, paddingTop: spacing.md, alignItems: 'center' },
  title: { fontSize: 25, fontWeight: '700', color: colors.ink, textAlign: 'center', letterSpacing: -0.5 },
  body: { fontSize: 15, lineHeight: 22, color: colors.inkSoft, textAlign: 'center', marginTop: spacing.sm, maxWidth: 340 },
  bottom: { paddingHorizontal: spacing.xl, gap: spacing.md },
  dots: { flexDirection: 'row', justifyContent: 'center', gap: 6, marginBottom: spacing.sm },
  dot: { width: 8, height: 6, borderRadius: 3, backgroundColor: colors.tileMuted },
  dotOn: { width: 24, backgroundColor: colors.forest },
  primary: { height: 54, borderRadius: radius.md + 2, backgroundColor: colors.forest, alignItems: 'center', justifyContent: 'center' },
  primaryText: { color: colors.white, fontSize: 16, fontWeight: '700' },
  secondary: { height: 54, borderRadius: radius.md + 2, borderWidth: 1.5, borderColor: colors.forest, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.white },
  secondaryText: { color: colors.forest, fontSize: 16, fontWeight: '700' },
  pressed: { opacity: 0.85, transform: [{ scale: 0.99 }] },
  stage: { width: 300, height: 290 },
  card: { position: 'absolute', backgroundColor: colors.white, borderRadius: 16, padding: 14, gap: 9, shadowColor: '#253420', shadowOpacity: 0.14, shadowRadius: 22, shadowOffset: { width: 0, height: 14 }, elevation: 6 },
  back: { top: 0, left: 0, width: 238 },
  front: { top: 128, left: 58, width: 238 },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardIcon: { width: 24, height: 24, borderRadius: 7, backgroundColor: colors.accentDeep, alignItems: 'center', justifyContent: 'center' },
  cardTitle: { fontSize: 12.5, fontWeight: '700', color: colors.ink },
  cardSub: { fontSize: 10.5, color: colors.inkSoft },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  rowLabel: { flex: 1, fontSize: 11.5, color: colors.ink, fontWeight: '600' },
  tag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 99, backgroundColor: colors.sageTint },
  tagText: { fontSize: 10, fontWeight: '700', color: colors.forest },
  progress: { height: 5, borderRadius: 3, backgroundColor: colors.tileMuted, overflow: 'hidden' },
  progressFill: { height: 5, borderRadius: 3, backgroundColor: colors.accentDeep },
  plan: { height: 86, borderWidth: 2.5, borderColor: colors.forest, borderRadius: 4, backgroundColor: '#F4F6EF', justifyContent: 'center', alignItems: 'center' },
  planWindow: { position: 'absolute', top: -3, left: '38%', width: '26%', height: 4, backgroundColor: '#A9C3D1' },
  planDoor: { position: 'absolute', bottom: -3, left: '12%', width: '20%', height: 4, backgroundColor: '#F4F6EF' },
  planDim: { fontSize: 10, fontWeight: '700', color: colors.accentDeep },
  bars: { flexDirection: 'row', alignItems: 'flex-end', gap: 10, height: 66, paddingHorizontal: 6 },
  bar: { flex: 1, borderRadius: 5, backgroundColor: colors.sageTint },
  bubble: { backgroundColor: colors.sageTint, borderRadius: 12, borderTopLeftRadius: 4, padding: 10 },
  bubbleText: { fontSize: 11.5, color: colors.ink, lineHeight: 16 },
  chips: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 9, paddingVertical: 5, borderRadius: 8, backgroundColor: colors.sageTint },
  chipText: { fontSize: 10.5, fontWeight: '700', color: colors.forest },
});
