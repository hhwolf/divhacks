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
  estimated?: boolean; dimensionsConfirmed?: boolean; deliveryCost?: number;
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
  supersedesRoomId?: string | null;
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

// Housing comparisons and guarded test payments. Payment amounts are integer USD cents.
export type OccupancyType = 'whole_apartment' | 'studio' | 'private_room' | 'shared_room';
export type ConditionCategory = 'insects' | 'rodents' | 'leaks' | 'plumbing' | 'heat_hot_water' | 'other';
export interface ConditionObservation {
  category: ConditionCategory; status: 'ongoing' | 'resolved' | 'unknown'; severity: 'minor' | 'moderate' | 'severe' | 'unknown';
  observedAt: string; source: 'user' | 'photo' | 'public_record'; scope: 'unit' | 'building' | 'area'; note: string; photoIds: string[];
}
export interface RentalComparable {
  id: string; unitKey: string; sourceUrl: string; observedAt: string; occupancyType: OccupancyType;
  rentCents: number; areaSqFt: number; areaConfirmed: boolean; latitude: number; longitude: number;
  bedrooms: number | null; bathrooms: number | null; leaseMonths: number | null; furnished: boolean | null; utilitiesIncluded: boolean | null;
  sharedAmenities: string; conditionsDocumented: boolean; conditions: ConditionObservation[]; provenance: 'user' | 'rentcast' | 'fixture';
}
export interface HousingProfile {
  roomId: string; address?: string | null; zip?: string | null; apartment?: string | null; bbl?: string | null; bin?: string | null;
  latitude?: number | null; longitude?: number | null; askingRent: number; occupancyType: OccupancyType; scanCoverage: 'room' | 'whole_apartment';
  measurementConfirmed: boolean; confirmedAreaSqFt?: number | null; bedrooms?: number | null; bathrooms?: number | null; leaseMonths: number;
  utilitiesIncluded: boolean; furnished: boolean; conditions: ConditionObservation[]; comparables: RentalComparable[]; dataMode: 'demo' | 'real';
  declaredIssues?: string[]; depositRequested?: number | null; applicationFee?: number | null;
}
export interface SourceInfo { source: string; status: 'demo' | 'available' | 'unavailable' | 'not_applicable'; url: string; retrievedAt: string; observedAt?: string | null; note: string; permittedUse: string }
export interface BuildingRecord { id: string; kind: 'violation' | 'inspection' | 'complaint'; scope: 'unit' | 'building' | 'area'; summary: string; status: string; severity: string; observedAt: string; sourceUrl: string; bbl: string; apartment?: string | null; demo: boolean }
export interface RentRange { low: number; mid: number; high: number }
export interface SpaceQuality { floorAreaSqFt: number; usableAreaSqFt: number; openFloorPct: number; ceilingHeightFt: number; windowCount: number }
export interface RentAssessment {
  id: string; userId: string; roomId: string; layoutId?: string | null; profile: HousingProfile; spaceQuality: SpaceQuality;
  status: 'demo' | 'estimated' | 'insufficient_data' | 'legacy_demo'; methodVersion: string; estimatedFairRange: RentRange | null;
  conditionMatchedRange: RentRange | null; conditionDifference: number | null; askingRent: number; deltaVsMid: number | null; pricePerSqFt: number;
  comparables: RentalComparable[]; conditionComparableIds: string[]; explanation: string[]; sources: SourceInfo[]; buildingRecords: BuildingRecord[];
  notices: string[]; createdAt: string; updatedAt: string;
}
export type PaymentPurpose = 'rent_payment' | 'deposit' | 'application_fee' | 'screening_fee' | 'broker_fee' | 'other' | 'furniture_purchase';
export interface Tenancy {
  id: string; userId: string; roomId: string; mode: 'demo' | 'test'; recipientId: string; recipientName: string; recipientVerified: boolean;
  supportedArrangement: boolean; leaseDocumented: boolean; monthlyRentCents: number; screeningActualCostCents: number | null;
  screeningDocumentsProvided: boolean; recentScreeningReport: boolean; depositAlreadyPaidCents: number; screeningAlreadyPaidCents: number;
  brokerHiredBy: 'landlord' | 'tenant' | 'unknown'; contact: string; refundPolicy: string; createdAt: string;
}
export interface QuoteRequest { tenancyId: string; purpose: PaymentPurpose; amountCents: number; rentalPeriod: string }
export interface PaymentQuote extends QuoteRequest {
  id: string; userId: string; roomId: string; recipientId: string; recipientName: string; currency: 'usd'; mode: 'demo' | 'test';
  decision: 'ready' | 'blocked' | 'needs_review'; reasons: string[]; ruleVersion: string; ruleSources: string[]; contact: string; refundPolicy: string; expiresAt: string; createdAt: string;
}
export interface PaymentRecord {
  id: string; quoteId: string; userId: string; roomId: string; tenancyId: string; recipientId: string; purpose: PaymentPurpose; rentalPeriod: string;
  amountCents: number; currency: 'usd'; mode: 'demo' | 'test'; status: 'created' | 'pending' | 'succeeded' | 'failed' | 'canceled' | 'expired' | 'refunded' | 'disputed';
  sessionId: string | null; paymentIntentId: string | null; checkoutUrl: string | null; refundedCents: number; createdAt: string; updatedAt: string;
}
export interface EvidencePhoto { id: string; roomId: string; createdAt: string; mimeType: string; size: number; mode: 'demo' | 'private' }
export interface AddressCandidate { label: string; latitude: number; longitude: number; bbl: string | null; bin: string | null }
