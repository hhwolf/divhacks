import { useLocalSearchParams } from 'expo-router';
import React, { useEffect, useState } from 'react';

import { api } from '../../src/api';
import { EditorWebView } from '../../src/components/EditorWebView';

export default function EditorScreen() {
  const { layoutId, roomId: roomIdParam, fps } = useLocalSearchParams<{ layoutId: string; roomId?: string; fps?: string }>();
  const [roomId, setRoomId] = useState<string | undefined>(roomIdParam);

  // Resolve the room id in the background so the editor can hand off to /ask and /variants.
  useEffect(() => {
    if (roomId || !layoutId) return;
    let cancelled = false;
    api
      .getLayout(layoutId)
      .then((l) => {
        if (!cancelled) setRoomId(l.roomId);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [layoutId, roomId]);

  if (!layoutId) return null;
  return <EditorWebView key={layoutId} route={`/layout/${encodeURIComponent(layoutId)}`} layoutId={layoutId} roomId={roomId} fpsProbe={fps === '1'} />;
}
