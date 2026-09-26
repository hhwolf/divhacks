// Canonical TypeScript types mirroring packages/contracts/schemas/*.json.
// Meters everywhere. x runs along wall 0; z runs toward the viewer. Rotation in degrees about vertical.

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
  /** Per material-slot colours (Kenney slot names: wood, carpet, metal, …) for realistic, varied palettes. */
  materials?: Record<string, string>;
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
export interface RoomElement { id: string; label: string; furnitureIds?: string[]; custom?: boolean; zone?: { w: number; d: number } | null }
export interface Room {
  id: string; userId?: string | null; name: string; skeleton: RoomSkeleton; source: 'scan' | 'manual' | 'sample'; createdAt?: string;
  spaceTypes?: SpaceType[] | string[]; elements?: RoomElement[]; detectedObjects?: LayoutItem[];
}

export type Intent = 'fit_item' | 'make_space' | 'keep_clear' | 'compare' | 'rent_check' | 'payment_check' | 'housing_quality' | 'clarify';
export interface PlanConstraint { type: 'lock' | 'adjacent' | 'keep_clear' | 'clear_zone'; item?: string; feature?: 'window' | 'door' | 'outlet' | 'wall'; w_m?: number; d_m?: number; label?: string; optional?: boolean }
export interface PlanAction { type: 'add' | 'move' | 'remove' | 'rotate'; item: string; zone?: string; rotation?: number }
export interface AgentPlan { intent: Intent; variantName?: string; constraints?: PlanConstraint[]; actions?: PlanAction[]; reply: string; clarifyingQuestion?: string; preferencesLearned?: string[] }

// ---- Validation results (shared TS/Python shape; see fixtures/validation) ----
export type Severity = 'error' | 'warning';
export type RuleId = 'bounds' | 'overlap' | 'locked' | 'door_clearance' | 'window_keep_clear' | 'access_edge' | 'clear_zone' | 'walkable_path';
export interface Violation { rule: RuleId; severity: Severity; items: string[]; message: string }
export interface ValidationResult { violations: Violation[]; metrics: LayoutMetrics; blocked: boolean }

// ---- Bridge messages (Expo WebView <-> editor) ----
export type BridgeType =
  | 'host:hello' | 'editor:ready' | 'host:openLayout' | 'editor:layoutChanged' | 'editor:selection'
  | 'editor:snapshot' | 'host:units' | 'editor:metrics' | 'host:request' | 'editor:agentReply' | 'editor:navigate' | 'editor:log';
export interface BridgeMessage<T = unknown> { type: BridgeType; id?: string; payload?: T }

export type Units = 'imperial' | 'metric';

// ---- Rent reality check + guarded payment prototype ----
export type OccupancyType = 'whole_apartment' | 'studio' | 'private_room' | 'shared_room';
export type FloorMaterial = 'hardwood' | 'engineered_wood' | 'tile' | 'laminate' | 'concrete' | 'carpet' | 'vinyl' | 'unknown';
export type Confidence = 'high' | 'medium' | 'low';
export type PaymentPurpose = 'rent_payment' | 'deposit' | 'application_fee' | 'furniture_purchase';
export type PaymentStatus = 'mock' | 'ready' | 'blocked' | 'paid_test';
export interface HousingProfile {
  roomId: string;
  address?: string | null;
  zip?: string | null;
  borough?: string | null;
  neighborhood?: string | null;
  bbl?: string | null;
  source?: 'user' | 'fixture' | 'open_data';
  askingRent: number;
  depositRequested?: number | null;
  applicationFee?: number | null;
  utilitiesIncluded?: boolean;
  occupancyType?: OccupancyType;
  bedrooms?: number | null;
  declaredIssues?: string[];
}
export interface SpaceQuality {
  floorAreaSqFt: number;
  usableAreaSqFt: number;
  openFloorPct: number;
  ceilingHeightFt: number;
  windowCount: number;
  floorMaterial: FloorMaterial;
  materialConfidence: Confidence;
  conditionScore: number;
  issuePenalties: string[];
}
export interface RentRange { low: number; mid: number; high: number }
export interface SourceBreakdown { source: string; label: string; value: string }
export interface RentAssessment {
  id: string;
  roomId: string;
  layoutId?: string | null;
  profile: HousingProfile;
  spaceQuality: SpaceQuality;
  estimatedFairRange: RentRange;
  askingRent: number;
  deltaVsMid: number;
  pricePerSqFt: number;
  confidence: Confidence;
  explanation: string[];
  sourceBreakdown: SourceBreakdown[];
  legalFlags: string[];
  buildingHealthSignals: string[];
  createdAt: string;
  updatedAt: string;
}
export interface PaymentQuote {
  id: string;
  roomId?: string | null;
  assessmentId?: string | null;
  purpose: PaymentPurpose;
  amount: number;
  rentAmount?: number | null;
  status: PaymentStatus;
  guardrails: string[];
  checkoutUrl?: string | null;
  paymentRecordId?: string | null;
  createdAt: string;
  updatedAt: string;
}
