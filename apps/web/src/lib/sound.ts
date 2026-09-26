let ctx: AudioContext | null = null;
/** Soft "thunk" for drops. Created lazily on first use (needs a user gesture). */
export function thunk(): void {
  try {
    ctx ??= new AudioContext();
    const t = ctx.currentTime; const o = ctx.createOscillator(); const g = ctx.createGain();
    o.type = 'sine'; o.frequency.setValueAtTime(160, t); o.frequency.exponentialRampToValueAtTime(70, t + 0.12);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.008); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
    o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + 0.2);
  } catch { /* no audio */ }
}
