import { useSyncExternalStore } from 'react';

// Match the phone layout in styles.css, including the landscape native WebView.
export const COMPACT_EDITOR_QUERY = '(max-width: 600px), (max-width: 1100px) and (max-height: 600px)';
const subscribe = (changed: () => void) => {
  const query = window.matchMedia(COMPACT_EDITOR_QUERY);
  query.addEventListener('change', changed);
  return () => query.removeEventListener('change', changed);
};
export function useCompactEditor() {
  return useSyncExternalStore(subscribe, () => window.matchMedia(COMPACT_EDITOR_QUERY).matches, () => false);
}
