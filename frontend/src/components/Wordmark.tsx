// The ChargeLens wordmark: pure type, no icon. Space Grotesk, lowercase,
// two tones - "charge" in ink, "lens" in a blue gradient with a signature
// underline. Inside the splash screen the letters cascade in, then the
// whole mark flies to the sidebar brand slot and lands there.

import { useEffect, useRef, useState, type CSSProperties } from "react";

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

export function Splash({ flying }: { flying: boolean }) {
  const wmRef = useRef<HTMLDivElement>(null);
  const [flight, setFlight] = useState<CSSProperties>();

  useEffect(() => {
    if (!flying || !wmRef.current) return;
    // FLIP: measure where the sidebar wordmark sits and fly onto it
    const target = document.querySelector<HTMLElement>(".brand .wordmark");
    if (!target) return;
    const from = wmRef.current.getBoundingClientRect();
    const to = target.getBoundingClientRect();
    setFlight({
      transform: `translate(${to.left - from.left}px, ` +
                 `${to.top - from.top}px) scale(${to.height / from.height})`,
    });
  }, [flying]);

  return (
    <div className={`splash${flying ? " splash-fly" : ""}`} aria-hidden="true">
      <div className="splash-veil" />
      <div className="splash-inner">
        <div className="splash-wm" ref={wmRef} style={flight}>
          <Wordmark className="wordmark-xl" />
        </div>
      </div>
    </div>
  );
}
