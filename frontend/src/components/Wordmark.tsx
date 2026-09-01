// The ChargeLens wordmark: pure type, no icon. Space Grotesk, lowercase,
// two tones - "charge" in ink, "lens" in a blue gradient with a signature
// underline. Inside the splash screen the letters cascade in and the
// underline draws itself; everywhere else it renders static.

export function Wordmark({ className = "" }: { className?: string }) {
  const stagger = (offset: number) => (ch: string, i: number) => (
    <span
      key={`${offset}-${i}`}
      className="wm-ch"
      style={{ animationDelay: `${(offset + i) * 55}ms` }}
    >
      {ch}
    </span>
  );
  return (
    <span className={`wordmark ${className}`}>
      <span className="wm-part">{[..."charge"].map(stagger(0))}</span>
      <span className="wm-part wm-lens">
        {[..."lens"].map(stagger(6))}
        <span className="wm-underline" aria-hidden="true" />
      </span>
    </span>
  );
}

export function Splash({ hiding }: { hiding: boolean }) {
  return (
    <div className={`splash${hiding ? " splash-hide" : ""}`} aria-hidden="true">
      <div className="splash-inner">
        <Wordmark className="wordmark-xl" />
        <div className="splash-sub">Dispute intelligence</div>
      </div>
    </div>
  );
}
