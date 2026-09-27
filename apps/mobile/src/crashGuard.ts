// In a release build React Native turns any uncaught JS exception into a native abort (RCTFatal on the
// TurboModule queue). Replace that with an alert that shows the message and the top of the stack, so a bug
// on the phone is readable instead of a silent crash — and the app keeps running.
import { Alert } from 'react-native';

type Handler = (error: unknown, isFatal?: boolean) => void;
interface ErrorUtilsLike { getGlobalHandler?: () => Handler; setGlobalHandler?: (h: Handler) => void }

let installed = false;
export function installCrashGuard(): void {
  if (installed) return;
  installed = true;
  const eu = (globalThis as unknown as { ErrorUtils?: ErrorUtilsLike }).ErrorUtils;
  if (!eu?.setGlobalHandler) return;
  const previous = eu.getGlobalHandler?.();
  eu.setGlobalHandler((error, isFatal) => {
    const err = error as { message?: string; stack?: string; name?: string } | undefined;
    const message = err?.message ?? String(error);
    const stack = (err?.stack ?? '').split('\n').slice(0, 6).join('\n');
    console.error('[crashGuard]', isFatal ? 'fatal' : 'non-fatal', message, stack);
    try {
      Alert.alert(isFatal ? 'Something broke' : 'Warning', `${message}\n\n${stack}`.slice(0, 1200), [{ text: 'OK' }]);
    } catch {
      /* alert unavailable */
    }
    // Do not call `previous` for fatals in release: it would abort the process. Keep it for non-fatals.
    if (!isFatal && previous) previous(error, isFatal);
  });
}
