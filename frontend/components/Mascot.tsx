"use client";
import { useEffect, useRef } from "react";
import gsap from "gsap";

export default function Mascot() {
  const rootRef = useRef<HTMLDivElement>(null);
  const headRef = useRef<SVGGElement>(null);
  const leftPupilRef = useRef<SVGCircleElement>(null);
  const rightPupilRef = useRef<SVGCircleElement>(null);
  const leftLidRef = useRef<SVGRectElement>(null);
  const rightLidRef = useRef<SVGRectElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    const head = headRef.current;
    if (!root || !head) return;

    const quickX = gsap.quickTo(head, "x", { duration: 0.5, ease: "power3.out" });
    const quickRotate = gsap.quickTo(head, "rotation", { duration: 0.5, ease: "power3.out" });
    const pupilX = [leftPupilRef, rightPupilRef].map((r) =>
      r.current ? gsap.quickTo(r.current, "x", { duration: 0.4, ease: "power3.out" }) : null
    );
    const pupilY = [leftPupilRef, rightPupilRef].map((r) =>
      r.current ? gsap.quickTo(r.current, "y", { duration: 0.4, ease: "power3.out" }) : null
    );

    function handleMove(e: MouseEvent) {
      const rect = root!.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2 - 20;
      const dx = e.clientX - cx;
      const dy = e.clientY - cy;
      const dist = Math.hypot(dx, dy) || 1;
      const clampedDx = Math.max(-18, Math.min(18, dx / 14));
      const clampedDy = Math.max(-10, Math.min(10, dy / 20));

      quickX(Math.max(-10, Math.min(10, dx / 40)));
      quickRotate(Math.max(-8, Math.min(8, dx / 120)));
      pupilX.forEach((fn) => fn && fn(clampedDx));
      pupilY.forEach((fn) => fn && fn(clampedDy));
    }

    window.addEventListener("mousemove", handleMove);

    const blink = () => {
      const tl = gsap.timeline();
      [leftLidRef.current, rightLidRef.current].forEach((lid) => {
        if (!lid) return;
        tl.to(lid, { scaleY: 1, duration: 0.07, ease: "power1.in", transformOrigin: "center" }, 0);
      });
      tl.to([leftLidRef.current, rightLidRef.current], {
        scaleY: 0,
        duration: 0.1,
        ease: "power1.out",
        delay: 0.09,
      });
    };
    const blinkInterval = setInterval(blink, 2600 + Math.random() * 1800);

    gsap.to(root, {
      y: -6,
      duration: 1.8,
      repeat: -1,
      yoyo: true,
      ease: "sine.inOut",
    });

    return () => {
      window.removeEventListener("mousemove", handleMove);
      clearInterval(blinkInterval);
    };
  }, []);

  return (
    <div
      ref={rootRef}
      className="pointer-events-none fixed bottom-5 right-5 z-40 h-16 w-16 drop-shadow-lg sm:bottom-6 sm:right-6"
      aria-hidden="true"
    >
      <svg viewBox="0 0 100 100" className="h-full w-full overflow-visible">
        <circle cx="50" cy="54" r="38" fill="#329dd2" />
        <circle cx="50" cy="54" r="38" fill="url(#mascot-shine)" opacity="0.35" />
        <defs>
          <radialGradient id="mascot-shine" cx="35%" cy="30%" r="60%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
          </radialGradient>
        </defs>

        <g ref={headRef}>
          <ellipse cx="34" cy="52" rx="10" ry="11" fill="#ffffff" />
          <ellipse cx="66" cy="52" rx="10" ry="11" fill="#ffffff" />
          <circle ref={leftPupilRef} cx="34" cy="52" r="4.5" fill="#0f1a2e" />
          <circle ref={rightPupilRef} cx="66" cy="52" r="4.5" fill="#0f1a2e" />
          <rect ref={leftLidRef} x="23" y="41" width="22" height="22" fill="#329dd2" style={{ transformOrigin: "34px 52px" }} transform="scale(1, 0)" />
          <rect ref={rightLidRef} x="55" y="41" width="22" height="22" fill="#329dd2" style={{ transformOrigin: "66px 52px" }} transform="scale(1, 0)" />
          <path d="M 38 70 Q 50 78 62 70" stroke="#0f1a2e" strokeWidth="3" strokeLinecap="round" fill="none" />
        </g>

        <circle cx="50" cy="12" r="5" fill="#1f6b93" />
        <rect x="48.5" y="16" width="3" height="10" fill="#1f6b93" />
      </svg>
    </div>
  );
}
