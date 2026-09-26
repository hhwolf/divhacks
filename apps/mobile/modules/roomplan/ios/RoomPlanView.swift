// Expo view hosting Apple's RoomCaptureView. Emits `onCaptureStatus` { status, message? } to JS.

import ExpoModulesCore
#if canImport(RoomPlan)
import RoomPlan
#endif

final class RoomPlanView: ExpoView {
  let onCaptureStatus = EventDispatcher()

  #if canImport(RoomPlan)
  private var captureView: UIView?
  private var isSessionRunning = false
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
      onCaptureStatus(["status": "scanning"])
    }
    #endif
  }

  func stopSession() {
    #if canImport(RoomPlan)
    if #available(iOS 16.0, *), let view = captureView as? RoomCaptureView, isSessionRunning {
      view.captureSession.stop()
      isSessionRunning = false
      onCaptureStatus(["status": "processing"])
    }
    #endif
  }
}

#if canImport(RoomPlan)
@available(iOS 16.0, *)
extension RoomPlanView: RoomCaptureSessionDelegate, RoomCaptureViewDelegate {
  // Let RoomCaptureView run its own post-processing so it can hand us the final CapturedRoom.
  func captureView(shouldPresent roomDataForProcessing: CapturedRoomData, error: Error?) -> Bool {
    return true
  }

  func captureView(didPresent processedResult: CapturedRoom, error: Error?) {
    if let error = error {
      onCaptureStatus(["status": "error", "message": error.localizedDescription])
      return
    }
    RoomPlanCoordinator.shared.setCapturedRoom(processedResult)
    onCaptureStatus(["status": "done"])
  }

  func captureSession(_ session: RoomCaptureSession, didEndWith data: CapturedRoomData, error: Error?) {
    if let error = error {
      onCaptureStatus(["status": "error", "message": error.localizedDescription])
    }
  }

  // NSCoding conformance required by RoomCaptureViewDelegate.
  func encode(with coder: NSCoder) {}
}
#endif
