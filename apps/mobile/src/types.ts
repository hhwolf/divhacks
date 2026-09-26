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

export type FurnitureCategory = 'bed' | 'desk' | 'seating' | 'storage' | 'table' | 'decor' | 'imported';
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
  estimated?: boolean;
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

export interface Room { id: string; userId?: string | null; name: string; skeleton: RoomSkeleton; source: 'scan' | 'manual' | 'sample'; createdAt?: string }

export type Intent = 'fit_item' | 'make_space' | 'keep_clear' | 'compare' | 'clarify';
export interface PlanConstraint { type: 'lock' | 'adjacent' | 'keep_clear' | 'clear_zone'; item?: string; feature?: 'window' | 'door' | 'outlet' | 'wall'; w_m?: number; d_m?: number; label?: string; optional?: boolean }
export interface PlanAction { type: 'add' | 'move' | 'remove' | 'rotate'; item: string; zone?: string; rotation?: number }
export interface AgentPlan { intent: Intent; variantName?: string; constraints?: PlanConstraint[]; actions?: PlanAction[]; reply: string; clarifyingQuestion?: string; preferencesLearned?: string[] }

export type Units = 'imperial' | 'metric';

// ---- API response shapes (see EXECUTION_PROMPT.md §4) ----
export interface RoomListEntry extends Room { layoutCount?: number }
export interface CreateRoomResponse { room: Room; currentLayout: Layout; layouts: Layout[] }
export interface RoomDetailResponse { room: Room; layouts: Layout[] }
export type AgentStatus = 'ok' | 'clarify' | 'rejected';
export interface AgentLinks { app?: string; web?: string; [k: string]: string | undefined }
export interface AgentRequestResponse { plan: AgentPlan | null; layout: Layout | null; reply: string; status: AgentStatus; links?: AgentLinks }
export interface HealthResponse { mode: 'mock' | 'live' | string; integrations: Record<string, 'live' | 'mock' | boolean | string> }

// ---- RoomPlan native module export ----
export interface ScannedObject { category: string; dims: Dims; center: { x: number; z: number }; yaw: number; furnitureKey?: string | null }
export interface RoomPlanExport { skeleton: RoomSkeleton; objects: ScannedObject[] }
