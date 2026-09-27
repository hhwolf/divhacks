const path = require('node:path');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);
// Goals review and the API use the same sample room geometry.
config.watchFolders = [...config.watchFolders, path.resolve(__dirname, '../../fixtures')];
module.exports = config;
