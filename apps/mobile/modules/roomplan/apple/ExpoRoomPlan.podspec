# Local Expo Module wrapping Apple RoomPlan. The pod / Swift module is named ExpoRoomPlan (not RoomPlan)
# so it never shadows the system `RoomPlan` framework that the sources import. JS still sees `RoomPlan`.
Pod::Spec.new do |s|
  s.name           = 'ExpoRoomPlan'
  s.version        = '0.1.0'
  s.summary        = 'RoomPlan (LiDAR room capture) bridge for FitCheck'
  s.description    = 'Hosts RoomCaptureView and exports a CapturedRoom as the app skeleton JSON.'
  s.author         = 'FitCheck'
  s.homepage       = 'https://github.com/divhacks/adaptive-room-planner'
  s.license        = { :type => 'MIT' }
  s.platforms      = { :ios => '16.0' }
  s.swift_version  = '5.9'
  s.source         = { :git => '' }
  s.static_framework = true

  s.dependency 'ExpoModulesCore'

  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'SWIFT_COMPILATION_MODE' => 'wholemodule',
  }

  s.source_files = '**/*.{h,m,mm,swift}'
  # RoomPlan is iOS 16+ and absent on some simulators; weak-link so the app still launches without it.
  s.weak_frameworks = 'RoomPlan'
end
