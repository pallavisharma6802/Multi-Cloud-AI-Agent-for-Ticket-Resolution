"use client";
import { useEffect, useRef } from "react";

type Ship = { x: number; y: number; scale: number; drift: number };

const SHIPS: Ship[] = [
  { x: 0.18, y: 0.62, scale: 1, drift: 0.6 },
  { x: 0.52, y: 0.78, scale: 0.75, drift: 0.9 },
  { x: 0.8, y: 0.55, scale: 0.9, drift: 0.4 },
];

function drawShip(ctx: CanvasRenderingContext2D, x: number, y: number, scale: number, lit: number) {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(scale, scale);
  const hullColor = `rgba(${95 + lit * 160}, ${116 + lit * 6}, ${137 - lit * 55}, ${0.35 + lit * 0.55})`;
  ctx.fillStyle = hullColor;
  ctx.beginPath();
  ctx.moveTo(-14, 0);
  ctx.lineTo(14, 0);
  ctx.lineTo(9, 8);
  ctx.lineTo(-9, 8);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = hullColor;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(0, -16);
  ctx.stroke();
  ctx.restore();
}

export default function LighthouseHero({ height = 180 }: { height?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let raf = 0;
    let width = 0;
    let dpr = 1;

    function resize() {
      if (!canvas) return;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.clientWidth;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
    }
    resize();
    window.addEventListener("resize", resize);

    const beaconX = 0.08;
    const beaconY = 0.35;
    let t = 0;

    function frame() {
      if (!ctx || !canvas) return;
      t += reduceMotion ? 0 : 0.006;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const bg = ctx.createLinearGradient(0, 0, 0, height);
      bg.addColorStop(0, "#0b2030");
      bg.addColorStop(1, "#080f1b");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, width, height);

      ctx.save();
      [0, 1, 2].forEach((i) => {
        const fx = width * (0.2 + i * 0.3) + Math.sin(t * 0.7 + i) * 30;
        const fy = height * (0.5 + 0.15 * Math.sin(t * 0.5 + i * 2));
        const r = 90 + i * 20;
        const fog = ctx.createRadialGradient(fx, fy, 0, fx, fy, r);
        fog.addColorStop(0, "rgba(159,176,198,0.08)");
        fog.addColorStop(1, "rgba(159,176,198,0)");
        ctx.fillStyle = fog;
        ctx.beginPath();
        ctx.arc(fx, fy, r, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.restore();

      const bx = width * beaconX;
      const by = height * beaconY;
      const angle = Math.sin(t) * 0.55;
      const beamLen = width * 0.95;

      ctx.save();
      ctx.translate(bx, by);
      ctx.rotate(angle);
      const beam = ctx.createLinearGradient(0, 0, beamLen, 0);
      beam.addColorStop(0, "rgba(255,122,82,0.22)");
      beam.addColorStop(0.5, "rgba(50,157,210,0.1)");
      beam.addColorStop(1, "rgba(50,157,210,0)");
      ctx.fillStyle = beam;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(beamLen, -beamLen * 0.11);
      ctx.lineTo(beamLen, beamLen * 0.11);
      ctx.closePath();
      ctx.fill();
      ctx.restore();

      ctx.beginPath();
      ctx.arc(bx, by, 4, 0, Math.PI * 2);
      ctx.fillStyle = "#ff4c2b";
      ctx.shadowColor = "#ff4c2b";
      ctx.shadowBlur = 10;
      ctx.fill();
      ctx.shadowBlur = 0;

      SHIPS.forEach((s) => {
        const sx = width * s.x + Math.sin(t * s.drift) * 10;
        const sy = height * s.y;
        const toShipAngle = Math.atan2(sy - by, sx - bx);
        const diff = Math.abs(((toShipAngle - angle + Math.PI) % (Math.PI * 2)) - Math.PI);
        const lit = Math.max(0, 1 - diff / 0.35);
        drawShip(ctx, sx, sy, s.scale, lit);
      });

      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, [height]);

  return (
    <canvas
      ref={canvasRef}
      style={{ height, width: "100%", display: "block" }}
      aria-hidden="true"
    />
  );
}
