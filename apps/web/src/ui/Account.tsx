import { useEffect, useState } from 'react';
import { auth } from '../lib/auth';

export function Account() {
  const [email, setEmail] = useState(''); const [code, setCode] = useState(''); const [sent, setSent] = useState(false);
  const [signedIn, setSignedIn] = useState(false); const [busy, setBusy] = useState(false); const [message, setMessage] = useState('');
  useEffect(() => { void auth?.auth.getSession().then(({ data }) => setSignedIn(!!data.session)); }, []);
  const submit = async () => {
    if (!auth) return;
    setBusy(true); setMessage('');
    try {
      const result = sent ? await auth.auth.verifyOtp({ email, token: code, type: 'email' }) : await auth.auth.signInWithOtp({ email });
      if (result.error) throw result.error;
      if (sent) location.assign('/'); else { setSent(true); setMessage('Check your email for the sign-in code.'); }
    } catch (e) { setMessage((e as Error).message); } finally { setBusy(false); }
  };
  return <section className="account" aria-label="Account">
    <b>{signedIn ? 'Private workspace' : 'Demo workspace'}</b>
    {!auth && <small>Sign-in is not configured. Demo sessions are separate; use sample data.</small>}
    {auth && !signedIn && <form onSubmit={(e) => { e.preventDefault(); void submit(); }}>
      <label>Email<input type="email" required value={email} onChange={(e) => { setEmail(e.target.value); setSent(false); }} /></label>
      {sent && <label>Email code<input required autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} /></label>}
      <button className="btn" disabled={busy}>{sent ? 'Verify and open private workspace' : 'Email a sign-in code'}</button>
      <small>Sign-in opens a separate private workspace. Demo rooms stay in this browser’s demo session.</small>
    </form>}
    {signedIn && <button className="btn" onClick={async () => { await auth?.auth.signOut(); location.assign('/'); }}>Sign out</button>}
    {message && <p role="status">{message}</p>}
  </section>;
}
