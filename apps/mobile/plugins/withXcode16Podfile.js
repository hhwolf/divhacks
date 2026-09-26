// Config plugin: let `pod install` run on Xcode 16.0.
//
// React Native 0.81 (Expo SDK 54) refuses to install pods unless `xcodebuild -version` reports >= 16.1
// (node_modules/react-native/scripts/cocoapods/utils.rb `check_minimum_required_xcode`). It is a plain
// version-string comparison, not a compiler requirement: the app, the prebuilt RN core and the
// ExpoRoomPlan Swift module all build with Xcode 16.0 / iOS 18.0 SDK. This Mac cannot install Xcode 26
// tonight, so we lower the gate to the version we actually have. Delete this plugin once Xcode >= 16.1
// is installed.
const { withDangerousMod } = require('expo/config-plugins');
const fs = require('fs');
const path = require('path');

const ANCHOR = 'require File.join(File.dirname(`node --print "require.resolve(\'react-native/package.json\')"`), "scripts/react_native_pods")\n';
const OVERRIDE =
  '# withXcode16Podfile: RN 0.81 gates pod install on Xcode >= 16.1; this machine has 16.0 (see plugins/withXcode16Podfile.js).\n' +
  "Helpers::Constants.define_singleton_method(:min_xcode_version_supported) { '16.0' }\n";

module.exports = function withXcode16Podfile(config) {
  return withDangerousMod(config, [
    'ios',
    (cfg) => {
      const podfile = path.join(cfg.modRequest.platformProjectRoot, 'Podfile');
      const src = fs.readFileSync(podfile, 'utf8');
      if (!src.includes(OVERRIDE)) {
        if (!src.includes(ANCHOR)) throw new Error('withXcode16Podfile: react_native_pods require line not found in ios/Podfile');
        fs.writeFileSync(podfile, src.replace(ANCHOR, ANCHOR + OVERRIDE));
      }
      return cfg;
    },
  ]);
};
