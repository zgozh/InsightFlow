"use client";

import { useEffect, useRef, useState } from "react";

import { useRenderActivity } from "@/core/dom/render-activity";

const CENTER_X = 480;
const CENTER_Y = 350;

const OUTER_RING_PIXELS = Array.from({ length: 42 }, (_, index) => {
  const angle = (index / 42) * Math.PI * 2;
  const x = CENTER_X + Math.cos(angle) * 214;
  const y = CENTER_Y + Math.sin(angle) * 84;
  const color = Math.sin(angle) > 0 ? "#ff7935" : "#df4a27";
  return { angle, x, y, color };
});

const INNER_RING_PIXELS = Array.from({ length: 34 }, (_, index) => {
  const angle = (index / 34) * Math.PI * 2;
  const x = CENTER_X + Math.cos(angle) * 154;
  const y = CENTER_Y + Math.sin(angle) * 56;
  const color = Math.sin(angle) > 0 ? "#ffbd62" : "#f05a2e";
  return { angle, x, y, color };
});

const EVENT_HORIZON_PIXELS = Array.from({ length: 15 * 15 }, (_, index) => {
  const column = index % 15;
  const row = Math.floor(index / 15);
  const distance = Math.hypot(column - 7, row - 7);
  if (distance > 7.4) return null;
  return {
    x: CENTER_X - 90 + column * 12,
    y: CENTER_Y - 90 + row * 12,
    fill: distance > 6.1 ? "#28100b" : "#030305",
  };
}).filter((pixel) => pixel !== null);

const PARTICLES = Array.from({ length: 18 }, (_, index) => ({
  phase: (index / 18) * Math.PI * 2,
  speed: index % 3 === 0 ? 0.00019 : 0.00012,
  radius: 0.78 + (index % 4) * 0.075,
  size: index % 5 === 0 ? 3.5 : 2.5,
  alpha: 0.4 + (index % 3) * 0.15,
}));

/** 原创像素吸积环始终静态可见；Canvas 只负责少量绕行粒子的动态增强。 */
export function PixelBlackHole() {
  const sceneRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderParticles = useRenderActivity(sceneRef, false);
  const [canvasReady, setCanvasReady] = useState(false);

  useEffect(() => {
    if (!renderParticles) {
      setCanvasReady(false);
      return;
    }

    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) {
      setCanvasReady(false);
      return;
    }

    let running = true;
    let frame = 0;
    setCanvasReady(true);

    const draw = (time: number) => {
      if (!running) return;
      const { width, height } = canvas.getBoundingClientRect();
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
      const pixelWidth = Math.max(1, Math.round(width * pixelRatio));
      const pixelHeight = Math.max(1, Math.round(height * pixelRatio));
      if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
        canvas.width = pixelWidth;
        canvas.height = pixelHeight;
      }

      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      context.imageSmoothingEnabled = false;
      context.clearRect(0, 0, width, height);

      const mobile = width < 600;
      const particleCount = mobile ? 7 : 14;
      const centerX = width * 0.5;
      const centerY = height * 0.48;
      const radiusX = Math.min(width * (mobile ? 0.34 : 0.28), 240);
      const radiusY = Math.min(height * 0.14, 116);
      const seconds = time;

      for (let index = 0; index < particleCount; index += 1) {
        const particle = PARTICLES[index];
        if (!particle) continue;
        const angle = particle.phase + seconds * particle.speed;
        const x = centerX + Math.cos(angle) * radiusX * particle.radius;
        const y = centerY + Math.sin(angle) * radiusY * particle.radius;
        context.globalAlpha = particle.alpha;
        context.fillStyle = index % 4 === 0 ? "#ffc06b" : "#ff6934";
        context.fillRect(x, y, particle.size, particle.size);
      }
      context.globalAlpha = 1;
      frame = window.requestAnimationFrame(draw);
    };

    frame = window.requestAnimationFrame(draw);
    return () => {
      running = false;
      window.cancelAnimationFrame(frame);
    };
  }, [renderParticles]);

  return (
    <div
      ref={sceneRef}
      className="pointer-events-none absolute inset-0 overflow-hidden"
      aria-hidden="true"
    >
      <svg
        data-testid="black-hole-static"
        className="absolute inset-0 size-full"
        viewBox="0 0 960 700"
        preserveAspectRatio="xMidYMid slice"
        focusable="false"
      >
        <defs>
          <radialGradient id="black-hole-glow">
            <stop offset="0" stopColor="#ff6327" stopOpacity="0.22" />
            <stop offset="0.55" stopColor="#7e241b" stopOpacity="0.12" />
            <stop offset="1" stopColor="#070709" stopOpacity="0" />
          </radialGradient>
        </defs>
        <ellipse
          cx={CENTER_X}
          cy={CENTER_Y}
          rx="360"
          ry="230"
          fill="url(#black-hole-glow)"
        />
        <g transform={`rotate(-13 ${CENTER_X} ${CENTER_Y})`}>
          {OUTER_RING_PIXELS.map((pixel, index) => (
            <rect
              key={`outer-${index}`}
              x={pixel.x - 15}
              y={pixel.y - 9}
              width="30"
              height="18"
              transform={`rotate(${(pixel.angle * 180) / Math.PI + 90} ${pixel.x} ${pixel.y})`}
              fill={pixel.color}
              opacity="0.98"
              shapeRendering="crispEdges"
            />
          ))}
          {INNER_RING_PIXELS.map((pixel, index) => (
            <rect
              key={`inner-${index}`}
              x={pixel.x - 10}
              y={pixel.y - 7}
              width="20"
              height="14"
              transform={`rotate(${(pixel.angle * 180) / Math.PI + 90} ${pixel.x} ${pixel.y})`}
              fill={pixel.color}
              shapeRendering="crispEdges"
            />
          ))}
        </g>
        <ellipse
          cx={CENTER_X}
          cy={CENTER_Y}
          rx="91"
          ry="91"
          fill="#09080b"
          shapeRendering="crispEdges"
        />
        <g shapeRendering="crispEdges">
          {EVENT_HORIZON_PIXELS.map((pixel, index) => (
            <rect
              key={`horizon-${index}`}
              x={pixel.x}
              y={pixel.y}
              width="12"
              height="12"
              fill={pixel.fill}
            />
          ))}
          <rect x="280" y="251" width="7" height="7" fill="#ffc06b" />
          <rect x="680" y="449" width="6" height="6" fill="#ff6934" />
          <rect x="357" y="515" width="5" height="5" fill="#d3492e" />
          <rect x="603" y="197" width="5" height="5" fill="#ff9d45" />
        </g>
      </svg>
      <canvas
        ref={canvasRef}
        data-testid="black-hole-motion"
        data-motion-active={canvasReady ? "true" : "false"}
        className="absolute inset-0 size-full"
      />
    </div>
  );
}
