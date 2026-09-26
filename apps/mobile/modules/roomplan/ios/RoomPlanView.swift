// Expo view hosting Apple's RoomCaptureView. Emits `onCaptureStatus` to JS:
//   { status: 'idle' | 'scanning' | 'processing' | 'done' | 'error', message?, walls?, doors?, windows?, objects? }
// On devices without RoomPlan support the view stays an empty black box (the JS side never mounts it there anyway).

import ExpoModulesCore
#if canImport(RoomPlan)
import RoomPlan
#endif

final class RoomPlanView: ExpoView {
  let onCaptureStatus = EventDispatcher()
  private(set) var isSessionRunning = false

  #if canImport(RoomPlan)
  private var captureView: UIView?
  #endif

  required init(appContext: AppContext? = nil) {
    super.init(appContext: appContext)
    clipsToBounds = true
    backgroundColor = .black
    RoomPlanCoordinator.shared.view = self

    #if canImport(RoomPlan)
    if #available(iOS 16.0, *), RoomCaptureSession.isSupported {
      let view = RoomCaptureView(frame: bounds)
      view.captureSession.delegate = self
      view.delegate = self
      addSubview(view)
      captureView = view
    }
    #endif
  }

  override func layoutSubviews() {
    super.layoutSubviews()
    #if canImport(RoomPlan)
    captureView?.frame = bounds
    #endif
  }

  override func removeFromSuperview() {
    stopSession()
    if RoomPlanCoordinator.shared.view === self {
      RoomPlanCoordinator.shared.view = nil
    }
    super.removeFromSuperview()
  }

  func startSession() {
    #if canImport(RoomPlan)
    if #available(iOS 16.0, *), let view = captureView as? RoomCaptureView, !isSessionRunning {
      var config = RoomCaptureSession.Configuration()
      config.isCoachingEnabled = true
      view.captureSession.run(configuration: config)
      isSessionRunning = true
      onCaptureStatus(["status": "scanning", "walls": 0, "doors": 0, "windows": 0, "objects": 0])
    }
    #endif
  }

  func stopSession() {
    #if canImport(RoomPlan)
    if #available(iOS 16.0, *), let view = captureView as? RoomCaptureView, isSessionRunning {
      view.captureSession.stop()
      isSessionRunning = false
      onCaptureStatus(["status": "processing", "message": "Building the room model…"])
    }
    #endif
  }
}

#if canImport(RoomPlan)
@available(iOS 16.0, *)
extension RoomPlanView: RoomCaptureSessionDelegate, RoomCaptureViewDelegate {
  // MARK: RoomCaptureViewDelegate — let RoomCaptureView post-process so it hands us the final CapturedRoom.

  func captureView(shouldPresent roomDataForProcessing: CapturedRoomData, error: Error?) -> Bool {
    return true
  }

  func captureView(didPresent processedResult: CapturedRoom, error: Error?) {
    RoomPlanCoordinator.shared.finishCapture(processedResult, error: error)
    if let error = error {
      onCaptureStatus(["status": "error", "message": error.localizedDescription])
      return
    }
    onCaptureStatus(counts(processedResult, status: "done"))
  }

  // MARK: RoomCaptureSessionDelegate — live progress while scanning.

  func captureSession(_ session: RoomCaptureSession, didUpdate room: CapturedRoom) {
    guard isSessionRunning else { return }
    onCaptureStatus(counts(room, status: "scanning"))
  }

  func captureSession(_ session: RoomCaptureSession, didProvide instruction: RoomCaptureSession.Instruction) {
    guard isSessionRunning else { return }
    let text: String
    switch instruction {
    case .moveCloseToWall: text = "Move closer to the wall"
    case .moveAwayFromWall: text = "Move away from the wall"
    case .slowDown: text = "Slow down"
    case .turnOnLight: text = "Turn on more light"
    case .normal: text = "Keep scanning"
    case .lowTexture: text = "Point at more detail"
    @unknown default: text = "Keep scanning"
    }
    onCaptureStatus(["status": "scanning", "message": text])
  }

  func captureSession(_ session: RoomCaptureSession, didEndWith data: CapturedRoomData, error: Error?) {
    if let error = error {
      // Post-processing will not run; settle the pending stop() so JS is not left hanging.
      RoomPlanCoordinator.shared.finishCapture(nil, error: error)
      onCaptureStatus(["status": "error", "message": error.localizedDescription])
    }
  }

  private func counts(_ room: CapturedRoom, status: String) -> [String: Any] {
    return [
      "status": status,
      "walls": room.walls.count, "doors": room.doors.count, "windows": room.windows.count, "objects": room.objects.count,
    ]
  }
}
#endif
