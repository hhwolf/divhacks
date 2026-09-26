// Placeholder Expo Module for Apple RoomPlan. Compiles on any iOS 16+ SDK; the real skeleton export
// (walls -> segments, doors/windows -> wall offsets, objects -> seeded items) lands in a later iteration.
//
// JS name: `RoomPlan` (see ../index.ts). Swift module/pod name: `ExpoRoomPlan` so it does not shadow
// Apple's `RoomPlan` framework when we `import RoomPlan`.

import ExpoModulesCore
#if canImport(RoomPlan)
import RoomPlan
#endif

public class RoomPlanModule: Module {
  public func definition() -> ModuleDefinition {
    Name("RoomPlan")

    Function("isSupported") { () -> Bool in
      #if canImport(RoomPlan)
      if #available(iOS 16.0, *) {
        return RoomCaptureSession.isSupported
      }
      #endif
      return false
    }

    AsyncFunction("startCapture") { () -> Void in
      #if canImport(RoomPlan)
      if #available(iOS 16.0, *) {
        try RoomPlanCoordinator.shared.start()
        return
      }
      #endif
      throw RoomPlanUnavailableException()
    }

    AsyncFunction("stopCapture") { () -> Void in
      #if canImport(RoomPlan)
      if #available(iOS 16.0, *) {
        RoomPlanCoordinator.shared.stop()
        return
      }
      #endif
      throw RoomPlanUnavailableException()
    }

    // Returns { skeleton: { walls, doors, windows, floorPolygon, dimensions }, objects } — empty for now.
    AsyncFunction("exportSkeleton") { () -> [String: Any] in
      #if canImport(RoomPlan)
      if #available(iOS 16.0, *) {
        return RoomPlanCoordinator.shared.exportSkeleton()
      }
      #endif
      return RoomPlanCoordinator.emptyExport()
    }

    View(RoomPlanView.self) {
      Events("onCaptureStatus")
    }
  }
}

internal final class RoomPlanUnavailableException: Exception {
  override var reason: String {
    "RoomPlan is not available on this device (needs iOS 16+ and a LiDAR sensor)."
  }
}

/// Owns the single RoomCaptureSession and the last CapturedRoom so the module functions and the view agree.
internal final class RoomPlanCoordinator: NSObject {
  static let shared = RoomPlanCoordinator()

  /// The currently mounted view, set by RoomPlanView on mount / cleared on unmount.
  weak var view: RoomPlanView?

  static func emptyExport() -> [String: Any] {
    return [
      "skeleton": [
        "walls": [] as [[String: Any]],
        "doors": [] as [[String: Any]],
        "windows": [] as [[String: Any]],
        "floorPolygon": [] as [[Double]],
        "dimensions": ["l": 0.0, "w": 0.0, "h": 0.0],
      ],
      "objects": [] as [[String: Any]],
    ]
  }

  #if canImport(RoomPlan)
  @available(iOS 16.0, *)
  private var lastRoom: CapturedRoom? {
    get { _lastRoom as? CapturedRoom }
    set { _lastRoom = newValue }
  }
  private var _lastRoom: Any?

  @available(iOS 16.0, *)
  func start() throws {
    guard RoomCaptureSession.isSupported else { throw RoomPlanUnavailableException() }
    guard let view = view else {
      throw Exception(name: "RoomPlanViewNotMounted", description: "Mount <RoomPlanView> before calling startCapture().")
    }
    view.startSession()
  }

  @available(iOS 16.0, *)
  func stop() {
    view?.stopSession()
  }

  @available(iOS 16.0, *)
  func setCapturedRoom(_ room: CapturedRoom) {
    lastRoom = room
  }

  @available(iOS 16.0, *)
  func exportSkeleton() -> [String: Any] {
    // TODO(iteration 4): project lastRoom.walls/doors/windows/objects to the floor plane, re-base to the
    // min corner, and map categories to manifest keys. Until then return the empty skeleton.
    _ = lastRoom
    return RoomPlanCoordinator.emptyExport()
  }
  #endif
}
