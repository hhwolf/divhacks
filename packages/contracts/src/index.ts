// Canonical TypeScript types mirroring packages/contracts/schemas/*.json.
// Meters everywhere. x runs along wall 0; z runs toward the viewer. Rotation in degrees about vertical.

export interface WallSegment { x1: number; z1: number; x2: number; z2: number; height: number; id?: string; thickness?: number }
/** `wall`/`offset` locate the opening; `wallId`/`center` are the same fact by id/point. Openings (no door leaf) have `opening: true`. */
export interface Door { wall: number; offset: number; width: number; height?: number; swing: 'in' | 'out'; hinge: 'left' | 'right'; id?: string; wallId?: string; center?: [number, number]; opening?: boolean }
export interface Window { wall: number; offset: number; width: number; sillHeight: number; height: number; id?: string; wallId?: string; center?: [number, number] }
export interface Outlet { wall: number; offset: number }
export interface Dimensions { l: number; w: number; h: number }
export interface RoomSkeleton {
  walls: WallSegment[];
  doors: Door[];
  windows: Window[];
  floorPolygon: [number, number][];
  dimensions: Dimensions;
  outlets?: Outlet[];
  ceilingHeight?: number;
}

export type FurnitureCategory = 'bed' | 'desk' | 'seating' | 'storage' | 'table' | 'decor' | 'imported' | 'other';
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
  photoUrl?: string | null;
  price?: number | null;
  color?: string | null;
  estimated?: boolean;
  frontAxis?: '+z' | '-z' | '+x' | '-x';
  colors?: string[];
}

export type Rotation = 0 | 90 | 180 | 270;
export interface LayoutItem { id: string; furnitureId: string; x: number; z: number; rotation: Rotation; locked: boolean; color?: string | null }
export interface Zone { label: string; x: number; z: number; w: number; d: number; type?: 'clear' | 'keep_clear' }
export type Walkability = 'Good' | 'Tight' | 'Blocked';
export interface FreeRect { x: number; z: number; w: number; d: number; areaM2: number; fits: string }
export interface LayoutMetrics { openFloor: number; conflicts: number; walkability: Walkability; reachableStorage: number; largestFreeRect: FreeRect | null; openFloorPct?: number; warnings?: string[] }
export interface Layout {
  id: string;
  roomId: string;
  name: string;
  /** base = read-only original, current = the Current Room, variant = everything else. `isCurrent` mirrors kind === 'current'. */
  kind?: LayoutKind;
  isCurrent: boolean;
  parentLayoutId?: string | null;
  items: LayoutItem[];
  zones: Zone[];
  metrics?: LayoutMetrics | null;
  createdBy?: 'user' | 'agent' | 'system';
  requestText?: string | null;
  /** optimistic concurrency: send it back on PUT; a stale one is a 409 */
  version?: number;
  createdAt?: string;
  updatedAt?: string;
}
export type LayoutKind = 'base' | 'current' | 'variant';

export interface Room {
  id: string; userId?: string | null; name: string; skeleton: RoomSkeleton; source: 'scan' | 'manual' | 'sample';
  usdzUrl?: string | null; thumbnailUrl?: string | null; baseLayoutId?: string | null; currentLayoutId?: string | null;
  conversion?: { primCounts: Record<string, number>; metersPerUnit: number; upAxis: string; warnings: string[] } | null;
  createdAt?: string; updatedAt?: string | null;
}

// ---- Interior Designer agent (POST /agent/request). Gemini writes intent + constraints only; `placement`/`moves`/`zones` come from the solver. ----
export type Intent = 'fit_item' | 'make_space' | 'keep_clear' | 'rank_variants' | 'rent_check' | 'payment_check' | 'clarify';
export interface PlanItem { type: string; name?: string | null; w_m?: number | null; d_m?: number | null; h_m?: number | null; price_usd?: number | null }
export interface PlanConstraint { type: 'lock' | 'adjacent' | 'keep_clear' | 'clear_zone'; item?: string | null; feature?: 'window' | 'door' | 'outlet' | 'wall' | null; w_m?: number | null; d_m?: number | null; label?: string | null }
export interface Placement { item: string; name: string; furnitureId: string; x: number; z: number; rotation: Rotation }
export interface VariantRank { layoutId: string; rank: number; reason: string }
/** One Interior Designer option (interior-designer skill format); each is saved as its own named variant. */
export interface DesignOption {
  variantName: string; layoutId: string | null; explanation: string; tradeoff: string; moved: string[];
  placement?: Placement | null; moves: Placement[]; zones: Zone[]; relaxed: string[];
  validation: { ok: boolean; warnings: number; open_floor_pct: number };
}
export interface AgentPlan {
  intent: Intent; item?: PlanItem | null; constraints: PlanConstraint[]; variantName?: string | null; explanation: string;
  question?: string | null; ranking?: VariantRank[]; preferences?: string[];
  rent?: { askingRent?: number | null; zip?: string | null; occupancyType?: string | null; issues?: string[] } | null;
  payment?: { purpose: 'rent_payment' | 'deposit' | 'application_fee' | 'furniture_purchase'; amount?: number | null } | null;
  placement?: Placement | null; moves?: Placement[]; zones?: Zone[];
}

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
  stripeCheckoutUrl?: string | null;
  stripeSessionId?: string | null;
  createdAt: string;
  updatedAt: string;
}
