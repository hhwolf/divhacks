/** Warm flat background with faint hill/tree silhouettes along the bottom and thin corner frame marks (ref2/ref3). */
export function Backdrop() {
  return (
    <div className="backdrop" aria-hidden>
      <svg className="hills" viewBox="0 0 1920 420" preserveAspectRatio="none">
        <g fill="currentColor">
          <path d="M0 420V330c60-40 120-60 190-40 60 20 80 70 140 70s90-60 160-70 120 40 200 30 130-70 230-60 150 60 260 70 190-70 300-60 190 60 260 60 120-40 180-20v140z" />
          {Array.from({ length: 30 }, (_, i) => { const x = 40 + i * 64 + ((i * 37) % 23); const h = 40 + ((i * 53) % 70); return <path key={i} d={`M${x} 420 l14 ${-h} l14 ${h} z`} opacity={0.9} />; })}
        </g>
      </svg>
      <span className="corner tl" /><span className="corner tr" /><span className="corner bl" /><span className="corner br" />
    </div>
  );
}
