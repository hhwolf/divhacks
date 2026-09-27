import AsyncStorage from '@react-native-async-storage/async-storage';
import { randomUUID } from 'expo-crypto';

let pending: Promise<string> | null = null;
// Shared with the trusted editor WebView; never inject into an external listing or Checkout page.
export function nativeDemoSession(): Promise<string> {
  if (!pending) pending = (async () => {
    const saved = await AsyncStorage.getItem('arp-demo-session');
    if (saved) return saved;
    const value = randomUUID();
    await AsyncStorage.setItem('arp-demo-session', value);
    return value;
  })();
  return pending;
}
