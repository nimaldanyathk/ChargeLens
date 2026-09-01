// The ChargeLens wordmark: pure type, no icon. Space Grotesk, lowercase,
// two tones - "charge" in ink, "lens" in a blue gradient with a signature
// underline. In the splash the letters cascade in, the underline draws,
// then extends into a curved gradient swoosh that sweeps to the sidebar
// brand slot with the wordmark gliding in behind it.

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

const REDUCED = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function Splash({ flying }: { flying: boolean }) {
  const wmRef = useRef<HTMLDivElement>(null);
  const pathRef = useRef<SVGPathElement>(null);
  const [flight, setFlight] = useState<CSSProperties>();
  const [swoosh, setSwoosh] = useState<{ d: string; from: DOMRect; to: DOMRect } | null>(null);

  useEffect(() => {
    if (!flying || !wmRef.current) return;
    const target = document.querySelector<HTMLElement>(".brand .wordmark");
    const targetLine = document.querySelector<HTMLElement>(".brand .wm-underline");
    if (!target) return;
    const from = wmRef.current.getBoundingClientRect();
    const to = target.getBoundingClientRect();

    // FLIP flight for the wordmark, delayed so the swoosh leads the way
    setFlight({
      transform: `translate(${to.left - from.left}px, ` +
                 `${to.top - from.top}px) scale(${to.height / from.height})`,
      transitionDelay: REDUCED() ? "0s" : "0.28s",
    });

    if (REDUCED() || !targetLine) return;

    // the underline extends into a curved path toward the brand slot
    const line = wmRef.current.querySelector<HTMLElement>(".wm-underline");
    const lr = (line ?? wmRef.current).getBoundingClientRect();
    const tr = targetLine.getBoundingClientRect();
    const sx = lr.left + lr.width * 0.6, sy = lr.top + lr.height / 2;
    const ex = tr.left + tr.width * 0.5, ey = tr.top + tr.height / 2;
    const vw = window.innerWidth, vh = window.innerHeight;
    const d = `M ${sx} ${sy} ` +
      `C ${sx - vw * 0.30} ${sy + vh * 0.16}, ` +
      `${Math.max(ex - vw * 0.12, 8)} ${sy - vh * 0.34}, ` +
      `${ex + vw * 0.10} ${ey + vh * 0.10} ` +
      `S ${ex + 26} ${ey + 14}, ${ex} ${ey}`;
    setSwoosh({ d, from: lr, to: tr });
  }, [flying]);

  useEffect(() => {
    const path = pathRef.current;
    if (!swoosh || !path) return;
    const L = path.getTotalLength();
    // comet: the stroke draws forward from the underline, then its tail
    // releases and the whole line absorbs into the top-left landing point
    path.style.strokeDasharray = `${L}`;
    path.animate(
      [{ strokeDashoffset: L }, { strokeDashoffset: -L * 0.995 }],
      { duration: 1050, easing: "cubic-bezier(0.55, 0.06, 0.18, 1)",
        fill: "forwards" },
    );
  }, [swoosh]);

  return (
    <div className={`splash${flying ? " splash-fly" : ""}`} aria-hidden="true">
      <div className="splash-veil" />
      {swoosh && (
        <svg className="splash-swoosh"
             width={window.innerWidth} height={window.innerHeight}>
          <defs>
            <linearGradient id="swoosh-g" gradientUnits="userSpaceOnUse"
              x1={swoosh.from.left} y1={swoosh.from.top}
              x2={swoosh.to.left} y2={swoosh.to.top}>
              <stop offset="0" stopColor="#9db6ff" />
              <stop offset="1" stopColor="#305eff" />
            </linearGradient>
          </defs>
          <path ref={pathRef} d={swoosh.d} fill="none"
                stroke="url(#swoosh-g)" strokeWidth="3.2"
                strokeLinecap="round" />
        </svg>
      )}
      <div className="splash-inner">
        <div className="splash-wm" ref={wmRef} style={flight}>
          <Wordmark className="wordmark-xl" />
        </div>
      </div>
    </div>
  );
}
