// Safe JS wrapper around the local `RoomPlan` Expo Module (Swift, ./ios). Everything here degrades to
// `null` / `false` when the native module is absent (Expo Go, Simulator, Android, web) so no screen crashes.

import { requireNativeViewManager, requireOptionalNativeModule } from 'expo-modules-core';
import React from 'react';
import type { ViewProps } from 'react-native';

import type { RoomPlanExport } from '../../src/types';

export interface RoomPlanNativeModule {
  /** `RoomCaptureSession.isSupported` — true only on LiDAR iPhones/iPads running iOS 16+. */
  isSupported(): boolean;
  /** Starts the capture session shown by the mounted RoomPlanView. */
  startCapture(): Promise<void>;
  /** Stops the session; RoomPlan then finalizes the CapturedRoom. */
  stopCapture(): Promise<void>;
  /** Converts the last CapturedRoom into our skeleton JSON + detected objects. Empty skeleton if none. */
  exportSkeleton(): Promise<RoomPlanExport>;
}

export type CaptureStatus = 'idle' | 'scanning' | 'processing' | 'done' | 'error';
export interface RoomPlanViewProps extends ViewProps {
  onCaptureStatus?: (event: { nativeEvent: { status: CaptureStatus; message?: string } }) => void;
}

let cachedModule: RoomPlanNativeModule | null | undefined;

export function getRoomPlanModule(): RoomPlanNativeModule | null {
  if (cachedModule === undefined) {
    try {
      cachedModule = requireOptionalNativeModule<RoomPlanNativeModule>('RoomPlan');
    } catch {
      cachedModule = null;
    }
  }
  return cachedModule ?? null;
}

export function isRoomPlanAvailable(): boolean {
  return getRoomPlanModule() !== null;
}

/** True only when the native module is linked AND the device has LiDAR. */
export function isSupported(): boolean {
  const mod = getRoomPlanModule();
  if (!mod) return false;
  try {
    return Boolean(mod.isSupported());
  } catch {
    return false;
  }
}

let cachedView: React.ComponentType<RoomPlanViewProps> | null | undefined;

function getNativeView(): React.ComponentType<RoomPlanViewProps> | null {
  if (cachedView === undefined) {
    try {
      cachedView = isRoomPlanAvailable() ? requireNativeViewManager<RoomPlanViewProps>('RoomPlan') : null;
    } catch {
      cachedView = null;
    }
  }
  return cachedView ?? null;
}

/** Hosts Apple's RoomCaptureView. Renders nothing when the native module is unavailable. */
export function RoomPlanView(props: RoomPlanViewProps): React.ReactElement | null {
  const Native = getNativeView();
  if (!Native) return null;
  return React.createElement(Native, props);
}

export const EMPTY_EXPORT: RoomPlanExport = {
  skeleton: { walls: [], doors: [], windows: [], floorPolygon: [], dimensions: { l: 0, w: 0, h: 0 } },
  objects: [],
};
