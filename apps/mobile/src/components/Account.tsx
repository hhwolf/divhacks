import React, { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { nativeAuth } from '../auth';
import { Button, Field, Tile } from './ui';
import { type } from '../theme';

export function Account() {
  const [email, setEmail] = useState(''); const [code, setCode] = useState(''); const [sent, setSent] = useState(false); const [signedIn, setSignedIn] = useState(false); const [busy, setBusy] = useState(false); const [message, setMessage] = useState('');
  useEffect(() => { void nativeAuth?.auth.getSession().then(({ data }) => setSignedIn(!!data.session)); const listener = nativeAuth?.auth.onAuthStateChange((_event, session) => setSignedIn(!!session)); return () => listener?.data.subscription.unsubscribe(); }, []);
  const submit = async () => { if (!nativeAuth) return; setBusy(true); try { const result = sent ? await nativeAuth.auth.verifyOtp({ email, token: code, type: 'email' }) : await nativeAuth.auth.signInWithOtp({ email }); if (result.error) throw result.error; if (!sent) { setSent(true); setMessage('Check your email for the code.'); } else setMessage('Signed in.'); } catch (e) { setMessage((e as Error).message); } finally { setBusy(false); } };
  return <Tile><Text style={type.body}>{signedIn ? 'Private workspace' : 'Demo workspace'}</Text>
    {nativeAuth && !signedIn && <View><Field label="Email" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />{sent && <Field label="Email code" value={code} onChangeText={setCode} keyboardType="number-pad" />}<Button label={sent ? 'Verify code' : 'Email sign-in code'} disabled={busy} onPress={() => void submit()} /></View>}
    {signedIn && <Button label="Sign out" onPress={() => void nativeAuth?.auth.signOut()} />}{!!message && <Text style={type.small}>{message}</Text>}
  </Tile>;
}
