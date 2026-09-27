// Safe JS wrapper around the local `RoomPlan` Expo Module (Swift, ./ios). Everything here degrades to
// `null` / `false` when the native module is absent (Expo Go, Simulator, Android, web) so no screen crashes.

import { requireNativeViewManager, requireOptionalNativeModule } from 'expo-modules-core';
import React from 'react';
import type { ViewProps } from 'react-native';

import type { RoomPlanExport } from '../../src/types';

export interface RoomPlanNativeModule {
  /** `RoomCaptureSession.isSupported` — true only on LiDAR iPhones/iPads running iOS 16+. */
  isSupported(): boolean;
  /** Camera permission as iOS reports it. */
  cameraPermission(): CameraPermission;
  /** Prompts for camera access if it was never asked; resolves with the resulting state. */
  requestCameraPermission(): Promise<CameraPermission>;
  /** Starts the capture session shown by the mounted RoomPlanView. Rejects (`CameraPermissionDenied`) when the camera is off, or if no view is mounted. */
  startCapture(): Promise<void>;
  /**
   * Stops the session and resolves only once RoomPlan has finished post-processing the final CapturedRoom
   * (or rejects on failure / 30 s timeout), so `exportSkeleton()` can be called right after.
   */
  stopCapture(): Promise<void>;
  /** Projects the last CapturedRoom into our skeleton JSON + seeded `objects`. Empty skeleton if nothing captured. */
  exportSkeleton(): Promise<RoomPlanExport>;
}

export type CameraPermission = 'authorized' | 'denied' | 'restricted' | 'notDetermined';
export type CaptureStatus = 'idle' | 'scanning' | 'processing' | 'done' | 'error';
export type RoomPlanCapabilityReason = 'ready' | 'native-module-missing' | 'unsupported-device';
export interface RoomPlanCapability {
  moduleLinked: boolean;
  supported: boolean;
  reason: RoomPlanCapabilityReason;
}
/** Payload of `onCaptureStatus`. Counts are live while scanning (didUpdate) and final on `done`. */
export interface CaptureProgress {
  status: CaptureStatus;
  /** Coaching instruction ("Slow down", "Move closer to the wall") or an error description. */
  message?: string;
  walls?: number;
  doors?: number;
  windows?: number;
  objects?: number;
}
export interface RoomPlanViewProps extends ViewProps {
  onCaptureStatus?: (event: { nativeEvent: CaptureProgress }) => void;
}

/** Dev-only stand-in so the LiveScan screen can be exercised on a simulator: EXPO_PUBLIC_MOCK_ROOMPLAN=1. */
const MOCK = process.env.EXPO_PUBLIC_MOCK_ROOMPLAN === '1';
let mockListeners: Array<(e: { nativeEvent: CaptureProgress }) => void> = [];
const mockModule: RoomPlanNativeModule = {
  isSupported: () => true,
  cameraPermission: () => 'authorized',
  requestCameraPermission: async () => 'authorized',
  startCapture: async () => {
    let n = 0;
    const tick = () => { n++; mockListeners.forEach((l) => l({ nativeEvent: { status: 'scanning', walls: Math.min(4, n), doors: n > 2 ? 1 : 0, windows: n > 3 ? 1 : 0, objects: n > 4 ? 2 : 0, message: n % 2 ? 'Keep scanning' : undefined } })); if (n < 6) setTimeout(tick, 400); };
    setTimeout(tick, 300);
  },
  stopCapture: async () => { mockListeners.forEach((l) => l({ nativeEvent: { status: 'done', walls: 4, doors: 1, windows: 1, objects: 2 } })); },
  exportSkeleton: async () => ({ ...EMPTY_EXPORT, skeleton: { walls: [{ x1: 0, z1: 0, x2: 3.4, z2: 0, height: 2.7 }, { x1: 3.4, z1: 0, x2: 3.4, z2: 3, height: 2.7 }, { x1: 3.4, z1: 3, x2: 0, z2: 3, height: 2.7 }, { x1: 0, z1: 3, x2: 0, z2: 0, height: 2.7 }], doors: [{ wall: 2, offset: 0.3, width: 0.9, height: 2, swing: 'in', hinge: 'right' }], windows: [{ wall: 0, offset: 1, width: 1.2, sillHeight: 0.9, height: 1.3 }], floorPolygon: [[0, 0], [3.4, 0], [3.4, 3], [0, 3]], dimensions: { l: 3.4, w: 3, h: 2.7 } }, objects: [{ furnitureId: 'bed_double', x: 0.7, z: 0.95, rotation: 0, locked: false }] }) as RoomPlanExport,
};

let cachedModule: RoomPlanNativeModule | null | undefined;

export function getRoomPlanModule(): RoomPlanNativeModule | null {
  if (cachedModule === undefined) {
    try {
      cachedModule = MOCK ? mockModule : requireOptionalNativeModule<RoomPlanNativeModule>('RoomPlan');
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

export function getRoomPlanCapability(): RoomPlanCapability {
  const mod = getRoomPlanModule();
  if (!mod) {
    return { moduleLinked: false, supported: false, reason: 'native-module-missing' };
  }
  try {
    const supported = Boolean(mod.isSupported());
    return { moduleLinked: true, supported, reason: supported ? 'ready' : 'unsupported-device' };
  } catch {
    return { moduleLinked: true, supported: false, reason: 'unsupported-device' };
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
  if (MOCK) return React.createElement(MockView, props);
  const Native = getNativeView();
  if (!Native) return null;
  return React.createElement(Native, props);
}
function MockView(props: RoomPlanViewProps) {
  React.useEffect(() => {
    const l = props.onCaptureStatus; if (!l) return;
    mockListeners.push(l); return () => { mockListeners = mockListeners.filter((x) => x !== l); };
  }, [props.onCaptureStatus]);
  return React.createElement(require('react-native').View, { style: [{ backgroundColor: '#222' }, props.style] });
}

export const EMPTY_EXPORT: RoomPlanExport = {
  skeleton: { walls: [], doors: [], windows: [], floorPolygon: [], dimensions: { l: 0, w: 0, h: 0 } },
  objects: [],
};
