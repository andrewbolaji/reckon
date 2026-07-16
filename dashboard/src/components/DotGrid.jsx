import { useEffect, useRef } from "react";

const GAP = 24;
const BASE_ALPHA = 0.12;
const BASE_RADIUS = 1.0;
const HOVER_RADIUS = 120;
const DOT_COLOR = [155, 130, 255];

export default function DotGrid() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const hero = canvas.parentElement;
    const ctx = canvas.getContext("2d");
    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    let W = 0,
      H = 0,
      dpr = 1,
      pts = [],
      mx = -999,
      my = -999,
      rafId = null,
      paused = false;

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = hero.clientWidth;
      H = hero.clientHeight;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      pts = [];
      for (let y = GAP; y < H; y += GAP)
        for (let x = GAP; x < W; x += GAP) pts.push({ x, y });
      if (reducedMotion) drawStatic();
    }

    function drawStatic() {
      ctx.clearRect(0, 0, W, H);
      for (const p of pts) {
        ctx.fillStyle = `rgba(${DOT_COLOR.join(",")},${BASE_ALPHA})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, BASE_RADIUS, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    function draw() {
      if (paused) return;
      ctx.clearRect(0, 0, W, H);
      for (const p of pts) {
        const d = Math.hypot(p.x - mx, p.y - my);
        const near = d < HOVER_RADIUS;
        const t = near ? 1 - d / HOVER_RADIUS : 0;
        const a = near ? BASE_ALPHA + t * 0.6 : BASE_ALPHA;
        const r = near ? BASE_RADIUS + t * 2.2 : BASE_RADIUS;
        ctx.fillStyle = `rgba(${DOT_COLOR.join(",")},${a})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fill();
      }
      rafId = requestAnimationFrame(draw);
    }

    function onMove(e) {
      const rect = canvas.getBoundingClientRect();
      mx = e.clientX - rect.left;
      my = e.clientY - rect.top;
    }

    function onLeave() {
      mx = -999;
      my = -999;
    }

    function onVisibility() {
      if (document.hidden) {
        paused = true;
        if (rafId) cancelAnimationFrame(rafId);
      } else {
        paused = false;
        if (!reducedMotion) rafId = requestAnimationFrame(draw);
      }
    }

    // Pause when offscreen
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) {
          paused = true;
          if (rafId) cancelAnimationFrame(rafId);
        } else {
          paused = false;
          if (!reducedMotion) rafId = requestAnimationFrame(draw);
        }
      },
      { threshold: 0 }
    );

    resize();
    hero.addEventListener("mousemove", onMove);
    hero.addEventListener("mouseleave", onLeave);
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", onVisibility);
    observer.observe(hero);

    if (!reducedMotion) rafId = requestAnimationFrame(draw);

    return () => {
      if (rafId) cancelAnimationFrame(rafId);
      hero.removeEventListener("mousemove", onMove);
      hero.removeEventListener("mouseleave", onLeave);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
      observer.disconnect();
    };
  }, []);

  return <canvas ref={canvasRef} className="dot-canvas" />;
}
