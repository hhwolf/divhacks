# roomplan (local Expo Module)

JS entry: `index.ts` — `getRoomPlanModule()`, `isSupported()`, `RoomPlanView`, all safe in Expo Go (return null/false).
Native: `ios/RoomPlanModule.swift` (JS name `RoomPlan`), `ios/RoomPlanView.swift` (hosts `RoomCaptureView`), `ios/ExpoRoomPlan.podspec`.

Autolinked via `expo-module.config.json` when the lead runs `npx expo prebuild` / `npx expo run:ios --device`.
`exportSkeleton()` currently returns an empty skeleton; the CapturedRoom -> skeleton projection is iteration 4.
