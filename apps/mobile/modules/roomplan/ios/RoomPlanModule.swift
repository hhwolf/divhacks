// Expo Module wrapping Apple RoomPlan. JS name: `RoomPlan` (see ../index.ts). Swift module / pod name: `ExpoRoomPlan`
// so it never shadows Apple's `RoomPlan` framework that these sources import.
//
// Surface:
//   isSupported(): Bool                 RoomCaptureSession.isSupported (LiDAR + iOS 16)
//   startCapture(): Promise<void>       runs the session inside the mounted <RoomPlanView>
//   stopCapture(): Promise<void>        stops the session and RESOLVES ONLY after RoomPlan hands back the final
//                                       CapturedRoom (or fails / times out), so exportSkeleton() right after is safe
//   exportSkeleton(): Promise<Export>   SkeletonExporter.export(lastRoom) — see SkeletonExporter.swift
//   <RoomPlanView onCaptureStatus>      { status, message?, walls?, doors?, windows?, objects? }

import ExpoModulesCore
#if canImport(RoomPlan)
import RoomPlan
#endif

public class RoomPlanModule: Module {
  public func definition() -> ModuleDefinition {
    Name("RoomPlan")

    Function("isSupported") { () -> Bool in
      return RoomPlanCoordinator.isSupported
    }

    AsyncFunction("startCapture") { () throws -> Void in
      #if canImport(RoomPlan)
      if #available(iOS 16.0, *) {
        try RoomPlanCoordinator.shared.start()
        return
      }
      #endif
      throw RoomPlanUnavailableException()
    }.runOnQueue(.main)

    AsyncFunction("stopCapture") { (promise: Promise) in
      #if canImport(RoomPlan)
      if #available(iOS 16.0, *) {
        RoomPlanCoordinator.shared.stop(promise)
        return
      }
      #endif
      promise.reject(RoomPlanUnavailableException())
    }.runOnQueue(.main)

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

/// Owns the last CapturedRoom and the pending stop() promise so the module functions and the view agree.
internal final class RoomPlanCoordinator: NSObject {
  static let shared = RoomPlanCoordinator()

  /// The currently mounted view, set by RoomPlanView on mount / cleared on unmount.
  weak var view: RoomPlanView?

  static var isSupported: Bool {
    #if canImport(RoomPlan)
    if #available(iOS 16.0, *) {
      return RoomCaptureSession.isSupported
    }
    #endif
    return false
  }

  static func emptyExport() -> [String: Any] {
    #if canImport(RoomPlan)
    if #available(iOS 16.0, *) {
      return SkeletonExporter.emptyExport()
    }
    #endif
    return [
      "skeleton": [
        "walls": [] as [[String: Any]], "doors": [] as [[String: Any]], "windows": [] as [[String: Any]],
        "floorPolygon": [] as [[Double]], "dimensions": ["l": 0.0, "w": 0.0, "h": 0.0],
      ] as [String: Any],
      "objects": [] as [[String: Any]],
    ]
  }

  #if canImport(RoomPlan)
  private var _lastRoom: Any?
  private var pendingStop: Promise?
  private var stopTimeout: DispatchWorkItem?

  @available(iOS 16.0, *)
  var lastRoom: CapturedRoom? {
    get { _lastRoom as? CapturedRoom }
    set { _lastRoom = newValue }
  }

  @available(iOS 16.0, *)
  func start() throws {
    guard RoomCaptureSession.isSupported else { throw RoomPlanUnavailableException() }
    guard let view = view else {
      throw Exception(name: "RoomPlanViewNotMounted", description: "Mount <RoomPlanView> before calling startCapture().")
    }
    lastRoom = nil
    view.startSession()
  }

  /// Stops the session; the promise is settled from `finishCapture` once RoomCaptureView finishes post-processing.
  @available(iOS 16.0, *)
  func stop(_ promise: Promise) {
    guard let view = view, view.isSessionRunning else {
      // Nothing running: resolve immediately so JS can still call exportSkeleton() on the previous result.
      promise.resolve()
      return
    }
    pendingStop?.reject(Exception(name: "RoomPlanStopSuperseded", description: "stopCapture() was called again."))
    pendingStop = promise
    let timeout = DispatchWorkItem { [weak self] in
      self?.finishCapture(nil, error: Exception(name: "RoomPlanTimeout", description: "RoomPlan did not finish processing within 30 s."))
    }
    stopTimeout = timeout
    DispatchQueue.main.asyncAfter(deadline: .now() + 30, execute: timeout)
    view.stopSession()
  }

  /// Called by the view's RoomCaptureViewDelegate with the final processed room (or an error).
  @available(iOS 16.0, *)
  func finishCapture(_ room: CapturedRoom?, error: Error?) {
    stopTimeout?.cancel()
    stopTimeout = nil
    if let room = room { lastRoom = room }
    guard let promise = pendingStop else { return }
    pendingStop = nil
    if let error = error, room == nil {
      promise.reject(Exception(name: "RoomPlanCaptureFailed", description: error.localizedDescription))
    } else {
      promise.resolve()
    }
  }

  @available(iOS 16.0, *)
  func exportSkeleton() -> [String: Any] {
    guard let room = lastRoom else { return SkeletonExporter.emptyExport() }
    return SkeletonExporter.export(room)
  }
  #endif
}
