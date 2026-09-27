// Wraps app.json. For local testing in the store Expo Go (`ARP_EXPO_GO=1 npx expo start --offline`), drop the link to the
// Expo account (`owner` + `extra.eas.projectId`): Expo Go demands a manifest signed by that account for linked projects,
// which needs `npx expo login` as a member of it. Unlinked projects load unsigned. EAS builds (no ARP_EXPO_GO) are unchanged.
module.exports = ({ config }) => {
  if (!process.env.ARP_EXPO_GO) return config;
  const { owner: _owner, ...rest } = config;
  const { eas: _eas, ...extra } = config.extra ?? {};
  return { ...rest, extra };
};
