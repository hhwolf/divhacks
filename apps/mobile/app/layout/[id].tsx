import { Redirect, useLocalSearchParams } from 'expo-router';
import React from 'react';

/** Deep link target: roomplanner://layout/{id} and https://<web>/layout/{id} both land here. */
export default function LayoutDeepLink() {
  const { id, reviewFurniture } = useLocalSearchParams<{ id: string; reviewFurniture?: string }>();
  if (!id) return <Redirect href="/" />;
  return (
    <Redirect
      href={{
        pathname: '/editor/[layoutId]',
        params: reviewFurniture ? { layoutId: id, reviewFurniture } : { layoutId: id },
      }}
    />
  );
}
