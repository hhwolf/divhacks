import { useLocalSearchParams } from 'expo-router';
import React from 'react';

import { EditorWebView } from '../../../src/components/EditorWebView';

/** Side-by-side compare view rendered by the web editor at /compare/:a/:b. */
export default function CompareScreen() {
  const { a, b, roomId } = useLocalSearchParams<{ a: string; b: string; roomId?: string }>();
  if (!a || !b) return null;
  return <EditorWebView key={`${a}:${b}`} route={`/compare/${encodeURIComponent(a)}/${encodeURIComponent(b)}`} roomId={roomId} />;
}
