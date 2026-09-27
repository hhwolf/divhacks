import { Redirect, useLocalSearchParams } from 'expo-router';
import React from 'react';

/** Deep link target: roomplanner://layout/{id} and https://<web>/layout/{id} both land here. */
export default function LayoutDeepLink() {
  const { id, reviewFurniture, generateFurniture } = useLocalSearchParams<{ id: string; reviewFurniture?: string; generateFurniture?: string }>();
  if (!id) return <Redirect href="/" />;
  const params = { layoutId: id, ...(reviewFurniture ? { reviewFurniture } : {}), ...(generateFurniture ? { generateFurniture } : {}) };
  return (
    <Redirect
      href={{
        pathname: '/editor/[layoutId]',
        params,
      }}
    />
  );
}
