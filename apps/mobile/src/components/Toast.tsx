import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { Animated, StyleSheet, Text } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, radius, shadow } from '../theme';

type Show = (message: string, opts?: { tone?: 'ink' | 'danger'; ms?: number }) => void;
const ToastContext = createContext<Show>(() => {});

export function useToast(): Show {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const insets = useSafeAreaInsets();
  const [msg, setMsg] = useState<{ text: string; tone: 'ink' | 'danger' } | null>(null);
  const opacity = useRef(new Animated.Value(0)).current;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = useCallback<Show>(
    (message, opts) => {
      if (timer.current) clearTimeout(timer.current);
      setMsg({ text: message, tone: opts?.tone ?? 'ink' });
      Animated.timing(opacity, { toValue: 1, duration: 150, useNativeDriver: true }).start();
      timer.current = setTimeout(() => {
        Animated.timing(opacity, { toValue: 0, duration: 250, useNativeDriver: true }).start(() => setMsg(null));
      }, opts?.ms ?? 2800);
    },
    [opacity],
  );

  const value = useMemo(() => show, [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {msg ? (
        <Animated.View
          pointerEvents="none"
          style={[
            styles.toast,
            { opacity, bottom: insets.bottom + 24, backgroundColor: msg.tone === 'danger' ? colors.danger : colors.ink },
          ]}
        >
          <Text style={styles.text}>{msg.text}</Text>
        </Animated.View>
      ) : null}
    </ToastContext.Provider>
  );
}

const styles = StyleSheet.create({
  toast: {
    position: 'absolute',
    left: 24,
    right: 24,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: radius.md,
    ...shadow.soft,
  },
  text: { color: colors.tile, fontSize: 14, fontWeight: '600', textAlign: 'center' },
});
