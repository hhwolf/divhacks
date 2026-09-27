import { useLocalSearchParams } from 'expo-router';
import React, { useEffect, useState } from 'react';

import { api } from '../../src/api';
import { EditorWebView } from '../../src/components/EditorWebView';

export default function EditorScreen() {
  const { layoutId, roomId: roomIdParam, fps, reviewFurniture } = useLocalSearchParams<{
    layoutId: string;
    roomId?: string;
    fps?: string;
    reviewFurniture?: string;
  }>();
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
  const route = reviewFurniture
    ? `/layout/${encodeURIComponent(layoutId)}?reviewFurniture=${encodeURIComponent(reviewFurniture)}`
    : `/layout/${encodeURIComponent(layoutId)}`;
  return <EditorWebView key={`${layoutId}:${reviewFurniture ?? ''}`} route={route} layoutId={layoutId} roomId={roomId} fpsProbe={fps === '1'} />;
}
