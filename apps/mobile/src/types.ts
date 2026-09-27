// Copied from packages/contracts/src/index.ts (the mobile app is installed with plain npm and is not
// part of the pnpm workspace). Keep in sync by hand. Meters everywhere; rotation in degrees.

export interface WallSegment { x1: number; z1: number; x2: number; z2: number; height: number }
export interface Door { wall: number; offset: number; width: number; height?: number; swing: 'in' | 'out'; hinge: 'left' | 'right' }
export interface Window { wall: number; offset: number; width: number; sillHeight: number; height: number }
export interface Outlet { wall: number; offset: number }
export interface Dimensions { l: number; w: number; h: number }
export interface RoomSkeleton {
  walls: WallSegment[];
  doors: Door[];
  windows: Window[];
  floorPolygon: [number, number][];
  dimensions: Dimensions;
  outlets?: Outlet[];
}

export type FurnitureCategory = 'bed' | 'desk' | 'seating' | 'storage' | 'table' | 'decor' | 'divider' | 'imported';
export type FurnitureKind = 'bed' | 'desk' | 'wardrobe' | 'dresser' | 'storage' | 'seating' | 'table' | 'decor' | 'floor';
export type FurnitureSource = 'preset' | 'link' | 'photo' | 'manual' | 'scan';
export interface Dims { w: number; d: number; h: number }
export interface FurnitureItem {
  id: string;
  userId?: string | null;
  name: string;
  category: FurnitureCategory;
  kind: FurnitureKind;
  dims: Dims;
  glbUrl?: string | null;
  thumbUrl?: string | null;
  source: FurnitureSource;
  sourceUrl?: string | null;
  price?: number | null;
  color?: string | null;
  estimated?: boolean; dimensionsConfirmed?: boolean; deliveryCost?: number;
  frontAxis?: '+z' | '-z' | '+x' | '-x';
  colors?: string[];
}

export type Rotation = 0 | 90 | 180 | 270;
export interface LayoutItem { id: string; furnitureId: string; x: number; z: number; rotation: Rotation; locked: boolean; color?: string | null }
export interface Zone { label: string; x: number; z: number; w: number; d: number }
export type Walkability = 'Good' | 'Tight' | 'Blocked';
export interface FreeRect { x: number; z: number; w: number; d: number; areaM2: number; fits: string }
export interface LayoutMetrics { openFloor: number; conflicts: number; walkability: Walkability; reachableStorage: number; largestFreeRect: FreeRect | null }
export interface Layout {
  id: string;
  roomId: string;
  name: string;
  isCurrent: boolean;
  parentLayoutId?: string | null;
  items: LayoutItem[];
  zones: Zone[];
  metrics?: LayoutMetrics | null;
  createdBy?: 'user' | 'agent' | 'system';
  requestText?: string | null;
  createdAt?: string;
  updatedAt?: string;
}

export type SpaceType = 'bedroom' | 'study' | 'living' | 'workout' | 'creative' | 'shared';
/** Something the user says the space needs (bed, desk, yoga zone…); `furnitureIds` are the catalog items that satisfy it. */
export interface RoomElement { id: string; label: string; furnitureIds: string[]; custom?: boolean; zone?: { w: number; d: number } | null }
export interface SpaceTypeInfo { id: SpaceType | string; label: string; icon: string }
export interface Room {
  id: string;
  userId?: string | null;
  name: string;
  skeleton: RoomSkeleton;
  source: 'scan' | 'manual' | 'sample';
  createdAt?: string;
  spaceTypes?: string[];
  elements?: RoomElement[];
  /** RoomPlan-detected furniture kept aside when the room was created clean (`seed: false`). */
  detectedObjects?: LayoutItem[];
}

export type Intent = 'fit_item' | 'make_space' | 'keep_clear' | 'compare' | 'clarify';
export interface PlanConstraint { type: 'lock' | 'adjacent' | 'keep_clear' | 'clear_zone'; item?: string; feature?: 'window' | 'door' | 'outlet' | 'wall'; w_m?: number; d_m?: number; label?: string; optional?: boolean }
export interface PlanAction { type: 'add' | 'move' | 'remove' | 'rotate'; item: string; zone?: string; rotation?: number }
export interface AgentPlan { intent: Intent; variantName?: string; constraints?: PlanConstraint[]; actions?: PlanAction[]; reply: string; clarifyingQuestion?: string; preferencesLearned?: string[] }

export type Units = 'imperial' | 'metric';

// ---- API response shapes (see EXECUTION_PROMPT.md §4) ----
export interface RoomListEntry extends Room { layoutCount?: number }
export interface CreateRoomResponse { room: Room; currentLayout: Layout; layouts: Layout[] }
export interface RoomDetailResponse { room: Room; layouts: Layout[] }
export interface SetupSuggestionsResponse { suggested: RoomElement[]; all: RoomElement[] }
export type AgentStatus = 'ok' | 'clarify' | 'rejected';
export interface AgentLinks { app?: string; web?: string; [k: string]: string | undefined }
export interface AgentRequestResponse { plan: AgentPlan | null; layout: Layout | null; reply: string; status: AgentStatus; links?: AgentLinks }
export interface HealthResponse { mode: 'mock' | 'live' | string; integrations: Record<string, 'live' | 'mock' | boolean | string> }

// ---- RoomPlan native module export (modules/roomplan/ios/SkeletonExporter.swift) ----
/** Seed item for the Current Room layout; exactly what POST /rooms expects in `objects`. */
export type ScannedObject = Omit<LayoutItem, 'id' | 'color'>;
/** Debug record of every RoomPlan object, including skipped kitchen/bath fixtures (`furnitureId` null). */
export interface DetectedObject { category: string; furnitureId: string | null; x: number; z: number; dims: Dims; yaw: number }
export interface RoomPlanExportMeta {
  source: 'roomplan';
  convention?: string;
  reason?: string;
  wallCount: number;
  doorCount?: number;
  windowCount?: number;
  detected?: DetectedObject[];
  skipped?: string[];
}
export interface RoomPlanExport { skeleton: RoomSkeleton; objects: ScannedObject[]; meta?: RoomPlanExportMeta }

// ---- Room setup flow (app/setup.tsx) ----
/**
 * A room the user has captured but not yet created: geometry exactly as POST /rooms accepts it
 * (a RoomPlan `skeleton` for scans, plain `dimensions` for manual entry) plus any detected objects.
 * Held in the zustand store between the scan/dimensions step and the setup screen.
 */
export interface RoomDraft {
  name: string;
  source: 'scan' | 'manual';
  skeleton?: RoomSkeleton;
  dimensions?: Dimensions;
  doors?: Door[];
  windows?: Window[];
  objects: ScannedObject[];
}
