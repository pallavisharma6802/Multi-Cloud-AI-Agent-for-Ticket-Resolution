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
      className="pointer-events-none fixed bottom-0 right-5 z-40 h-28 w-20 drop-shadow-lg sm:right-6"
      aria-hidden="true"
    >
      <svg viewBox="0 0 100 130" className="h-full w-full overflow-visible">
        {/* shoulders / headset-wearing support agent, torso anchored off-screen */}
        <path d="M 14 130 Q 14 96 50 92 Q 86 96 86 130 Z" fill="#cb8a2e" />
        <path d="M 14 130 Q 14 96 50 92 Q 86 96 86 130 Z" fill="#241b17" opacity="0.08" />

        <g ref={headRef}>
          {/* neck */}
          <rect x="43" y="78" width="14" height="14" rx="5" fill="#e8b98c" />
          {/* head */}
          <ellipse cx="50" cy="56" rx="24" ry="26" fill="#f0c89a" />
          {/* hair */}
          <path
            d="M 26 52 Q 24 24 50 22 Q 76 24 74 52 Q 74 38 62 36 Q 56 44 50 36 Q 44 44 38 36 Q 27 38 26 52 Z"
            fill="#4a332a"
          />
          {/* ears */}
          <circle cx="25" cy="58" r="4.5" fill="#e8b98c" />
          <circle cx="75" cy="58" r="4.5" fill="#e8b98c" />
          {/* headset band + mic, the one "robot" nod kept minimal */}
          <path d="M 25 50 Q 50 16 75 50" stroke="#241b17" strokeWidth="3" fill="none" strokeLinecap="round" />
          <circle cx="75" cy="50" r="3.5" fill="#241b17" />
          <path d="M 75 53 Q 72 66 60 70" stroke="#241b17" strokeWidth="2.5" fill="none" strokeLinecap="round" />
          <circle cx="60" cy="70" r="3" fill="#241b17" />

          {/* eyes */}
          <ellipse cx="40" cy="56" rx="6" ry="7" fill="#fff" />
          <ellipse cx="60" cy="56" rx="6" ry="7" fill="#fff" />
          <circle ref={leftPupilRef} cx="40" cy="56" r="3.2" fill="#241b17" />
          <circle ref={rightPupilRef} cx="60" cy="56" r="3.2" fill="#241b17" />
          <rect
            ref={leftLidRef}
            x="32"
            y="47"
            width="16"
            height="16"
            fill="#f0c89a"
            style={{ transformOrigin: "40px 56px" }}
            transform="scale(1, 0)"
          />
          <rect
            ref={rightLidRef}
            x="52"
            y="47"
            width="16"
            height="16"
            fill="#f0c89a"
            style={{ transformOrigin: "60px 56px" }}
            transform="scale(1, 0)"
          />
          {/* brows */}
          <path d="M 34 47 Q 40 44 46 47" stroke="#4a332a" strokeWidth="2" fill="none" strokeLinecap="round" />
          <path d="M 54 47 Q 60 44 66 47" stroke="#4a332a" strokeWidth="2" fill="none" strokeLinecap="round" />
          {/* nose + friendly smile */}
          <path d="M 50 58 Q 48 64 50 66" stroke="#d99a6b" strokeWidth="1.5" fill="none" strokeLinecap="round" />
          <path d="M 40 70 Q 50 78 60 70" stroke="#241b17" strokeWidth="2.5" strokeLinecap="round" fill="none" />
        </g>
      </svg>
    </div>
  );
}
