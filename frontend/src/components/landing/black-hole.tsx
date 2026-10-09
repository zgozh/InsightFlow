"use client";

import { useEffect, useRef, useState } from "react";

import { useRenderActivity } from "@/core/dom/render-activity";

/** 静态颗粒底景与动态层使用同一坐标系；不具备 Canvas 时仍保留完整构图。 */
export function BlackHole() {
  const sceneRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const active = useRenderActivity(sceneRef, false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context || !active) {
      setReady(false);
      return;
    }
    setReady(true);
    let frame = 0;
    let previous = 0;
    const draw = (time: number) => {
      frame = requestAnimationFrame(draw);
      // 限制到约 30fps，手机降低像素比与颗粒数量。
      if (time - previous < 32) return;
      previous = time;
      const { width, height } = canvas.getBoundingClientRect();
      const mobile = width < 768;
      const ratio = Math.min(devicePixelRatio || 1, mobile ? 1 : 1.5);
      if (
        canvas.width !== Math.round(width * ratio) ||
        canvas.height !== Math.round(height * ratio)
      ) {
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      const scale = Math.max(width / 1600, height / 1000);
      const offsetX = (width - 1600 * scale) * (mobile ? 0.69 : 0.5);
      const offsetY = (height - 1000 * scale) / 2;
      context.translate(offsetX + 1100 * scale, offsetY + 510 * scale);
      context.scale(scale, scale);
      context.rotate(-0.29);
      context.globalCompositeOperation = "lighter";
      for (let i = 0; i < (mobile ? 320 : 850); i++) {
        const seed = (i * 0.61803398875) % 1;
        const radius = 165 + ((i * 0.75487766) % 1) * 480;
        const angle = seed * Math.PI * 2 + time * 0.000025 * (650 / radius);
        const x = Math.cos(angle) * radius;
        const y = Math.sin(angle) * radius * 0.25;
        if (y < 0 && Math.hypot(x, y) < 133) continue;
        context.globalAlpha = (0.15 + seed * 0.48) * (1 - (radius - 165) / 650);
        context.fillStyle = i % 4 === 0 ? "#ffe5a6" : "#ff8b3e";
        context.beginPath();
        context.ellipse(x, y, 0.7 + seed, 0.5, angle, 0, Math.PI * 2);
        context.fill();
      }
      context.globalCompositeOperation = "source-over";
      context.globalAlpha = 1;
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [active]);

  return (
    <div
      ref={sceneRef}
      data-testid="hero-background"
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 overflow-hidden"
    >
      {/* 原创矢量背景独立于脚本、Canvas 与动效偏好。 */}
      <img
        data-testid="black-hole-static"
        src="/images/black-hole-scene.svg"
        alt=""
        className="absolute inset-0 h-full w-full object-cover object-[69%_50%] max-md:translate-y-24 md:object-center"
      />
      <canvas
        ref={canvasRef}
        data-testid="black-hole-motion"
        data-motion-active={ready ? "true" : "false"}
        className="absolute inset-0 size-full max-md:translate-y-24"
        style={{ opacity: active ? 1 : 0 }}
      />
    </div>
  );
}
