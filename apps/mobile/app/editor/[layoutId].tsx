import { useLocalSearchParams } from 'expo-router';
import React, { useEffect, useState } from 'react';

import { api } from '../../src/api';
import { EditorWebView } from '../../src/components/EditorWebView';

export default function EditorScreen() {
  const { layoutId, roomId: roomIdParam, fps, reviewFurniture, generateFurniture } = useLocalSearchParams<{
    layoutId: string;
    roomId?: string;
    fps?: string;
    reviewFurniture?: string;
    generateFurniture?: string;
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
  const query = new URLSearchParams();
  if (reviewFurniture) query.set('reviewFurniture', reviewFurniture);
  if (generateFurniture) query.set('generateFurniture', generateFurniture);
  const queryString = query.toString();
  const route = `/layout/${encodeURIComponent(layoutId)}${queryString ? `?${queryString}` : ''}`;
  return <EditorWebView key={`${layoutId}:${reviewFurniture ?? ''}:${generateFurniture ?? ''}`} route={route} layoutId={layoutId} roomId={roomId} fpsProbe={fps === '1'} />;
}
