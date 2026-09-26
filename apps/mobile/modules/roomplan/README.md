# roomplan (local Expo Module)

JS entry: `index.ts` — `getRoomPlanModule()`, `isSupported()`, `RoomPlanView`, `CaptureProgress`; all safe in Expo Go
(return null/false, the view renders nothing).

Native (Swift, `ios/`), pod / Swift module name `ExpoRoomPlan` so `import RoomPlan` is never shadowed; JS name `RoomPlan`:

- `RoomPlanModule.swift` — `isSupported()`, `startCapture()`, `stopCapture()` (resolves only after RoomPlan has post-processed
  the final `CapturedRoom`, 30 s timeout), `exportSkeleton()`; `RoomPlanCoordinator` owns the last room + pending promise.
- `RoomPlanView.swift` — `ExpoView` hosting `RoomCaptureView`; `RoomCaptureSessionDelegate` (live wall/door/window/object
  counts + coaching text) and `RoomCaptureViewDelegate` (final room). Emits `onCaptureStatus`.
- `SkeletonExporter.swift` — pure `CapturedRoom -> {skeleton, objects, meta}` projection. Convention is documented at the
  top of the file: x = RoomPlan.x, z = RoomPlan.z (no mirror), walls chained + corner-snapped into a loop, reversed to wind
  clockwise on screen, origin re-based to the min corner; openings -> `{wall, offset(start edge), width, height, sillHeight}`
  (parent via `parentIdentifier` on iOS 17, nearest wall otherwise); objects -> `{furnitureId, x, z, rotation, locked:false}`
  by category (bed→bed_double/bed_single by min horizontal extent ≥ 1.2 m, table→desk if a chair is within 1 m,
  storage→wardrobe/dresser by height ≥ 1.5 m, sofa, chair, television→tv_stand; kitchen/bath fixtures skipped and listed in
  `meta.skipped`). Rotation = yaw of the object's local X axis quantised to 0/90/180/270 (same handedness as three.js).

Everything is guarded with `#if canImport(RoomPlan)` + `@available(iOS 16, *)` + `RoomCaptureSession.isSupported`.
`fixtures/rooms/roomplan-export-sample.json` is a hand-authored export in exactly this shape (`meta` is debug-only and is
not sent to `POST /rooms`).

Autolinked via `expo-module.config.json` on `npx expo prebuild` / `npx expo run:ios --device`. Building needs the Xcode
that Expo SDK 57 requires (Swift tools 6.2 / Xcode 26); `SkeletonExporter.swift` also typechecks standalone with
`xcrun swiftc -typecheck -sdk "$(xcrun --sdk iphoneos --show-sdk-path)" -target arm64-apple-ios16.0 ios/SkeletonExporter.swift`.
