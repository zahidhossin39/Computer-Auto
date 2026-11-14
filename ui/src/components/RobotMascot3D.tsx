import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import type { MascotState } from "../types";
import {
  createMascotRig,
  setupMascotStudioLighting,
  type MascotPoseVariant,
} from "./mascotRig";

interface RobotMascot3DProps {
  state: MascotState;
  audioLevel: number;
  theme?: "dark" | "light";
  compact?: boolean;
  onClick?: () => void;
}

const CLICK_PLAYFUL_CYCLE: MascotPoseVariant[] = [
  "happy_sip",
  "executing",
  "guardrail",
  "processing",
];

const SvgFallbackMascot: React.FC<{
  state: MascotState;
  audioLevel: number;
  compact?: boolean;
  onClick?: () => void;
}> = ({ state, audioLevel, compact, onClick }) => {
  const scale = 1 + (state === "listening" ? audioLevel * 0.06 : 0);
  const isSipping = state === "processing";

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Mochi AI Companion"
      className="relative flex items-center justify-center w-full h-full cursor-pointer focus:outline-none group"
    >
      <svg
        viewBox="0 0 220 220"
        className="animate-float drop-shadow-xl transition-transform duration-300 group-hover:scale-105"
        style={{
          width: compact ? 104 : 186,
          height: compact ? 104 : 186,
          transform: `scale(${scale})`,
        }}
      >
        <defs>
          <radialGradient id="mochiBodyGrad" cx="46%" cy="34%" r="62%">
            <stop offset="0%" stopColor="#C9DC5E" />
            <stop offset="68%" stopColor="#B8CB4E" />
            <stop offset="100%" stopColor="#9EB13E" />
          </radialGradient>
          <radialGradient id="mochiFaceGrad" cx="50%" cy="48%" r="58%">
            <stop offset="0%" stopColor="#E4EC9E" />
            <stop offset="82%" stopColor="#DCE494" />
            <stop offset="100%" stopColor="#9BA94E" />
          </radialGradient>
          <radialGradient id="mochiFloorShadow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#7A5A9E" stopOpacity="0.45" />
            <stop offset="65%" stopColor="#8E72B5" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#8E72B5" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Soft Elliptical Lavender Floor Shadow */}
        <ellipse cx="110" cy="196" rx="64" ry="12" fill="url(#mochiFloorShadow)" />

        {/* Left Arm (+X viewer right) */}
        <ellipse
          cx="172"
          cy="126"
          rx="14"
          ry="28"
          transform="rotate(-8 172 126)"
          fill="#B2C549"
        />

        {/* Seamless Pear-Egg Mochi Body */}
        <path
          d="M 110 38 C 146 38 172 74 172 118 C 172 158 146 180 110 180 C 74 180 48 158 48 118 C 48 74 74 38 110 38 Z"
          fill="url(#mochiBodyGrad)"
        />

        {/* Sideways 6-Panel Baseball Cap */}
        <g transform="translate(114, 42) rotate(10)">
          {/* Cap Dome */}
          <path
            d="M -32 6 C -32 -18 32 -18 32 6 Z"
            fill="#C0D354"
            stroke="#8B7798"
            strokeWidth="3.2"
            strokeLinejoin="round"
          />
          {/* Meridian Seams */}
          <path
            d="M 0 -14 C -8 -6 -12 0 -14 6 M 0 -14 C 8 -6 12 0 14 6"
            fill="none"
            stroke="#8B7798"
            strokeWidth="2.6"
            strokeLinecap="round"
          />
          {/* Top Lime Button (Squatchee) */}
          <ellipse cx="0" cy="-15" rx="4.2" ry="2.6" fill="#C8DC5E" />
          {/* Flipped-up Curved Duckbill Brim */}
          <path
            d="M -34 4 C -46 -12 -18 -24 4 -2 C -10 4 -24 5 -34 4 Z"
            fill="#B8CB4E"
            stroke="#8B7798"
            strokeWidth="3.4"
            strokeLinejoin="round"
          />
        </g>

        {/* Recessed Stadium Face Window */}
        <rect
          x="74"
          y="68"
          width="72"
          height="42"
          rx="21"
          fill="url(#mochiFaceGrad)"
          stroke="#A3B352"
          strokeWidth="2"
        />

        {/* Temple Freckles */}
        <circle cx="65" cy="84" r="1.3" fill="#93A444" />
        <circle cx="62" cy="89" r="1.4" fill="#93A444" />
        <circle cx="66" cy="93" r="1.2" fill="#93A444" />
        <circle cx="155" cy="84" r="1.3" fill="#93A444" />
        <circle cx="158" cy="89" r="1.4" fill="#93A444" />
        <circle cx="154" cy="93" r="1.2" fill="#93A444" />

        {/* Facial Expressions in Deep Dusty Plum (#6F5C7C) */}
        {state === "ready" || state === "listening" ? (
          <g stroke="#6F5C7C" strokeLinecap="round" fill="none">
            <line x1="93" y1="84" x2="93" y2="94" strokeWidth="4.2" />
            <line x1="127" y1="84" x2="127" y2="94" strokeWidth="4.2" />
            {state === "listening" ? (
              <path d="M 106 91 Q 110 95 114 91 M 110 94 L 110 98" strokeWidth="3.2" />
            ) : (
              <path d="M 105 91 Q 110 96 115 91" strokeWidth="3.4" />
            )}
          </g>
        ) : state === "processing" ? (
          <g stroke="#6F5C7C" strokeLinecap="round" fill="none">
            <path d="M 86 88 Q 93 93 100 88" strokeWidth="3.5" />
            <path d="M 120 88 Q 127 93 134 88" strokeWidth="3.5" />
            <path d="M 109 88 C 113 88 113 95 109 95" strokeWidth="3.2" />
          </g>
        ) : state === "executing" ? (
          <g stroke="#6F5C7C" strokeLinecap="round" fill="none">
            <path d="M 86 91 Q 93 84 100 91" strokeWidth="3.5" />
            <path d="M 120 91 Q 127 84 134 91" strokeWidth="3.5" />
            <path d="M 105 92 Q 110 97 115 92" strokeWidth="3.4" />
          </g>
        ) : (
          <g stroke="#6F5C7C" strokeLinecap="round" strokeLinejoin="round" fill="none">
            <path d="M 87 84 L 96 89 L 87 94" strokeWidth="3.4" />
            <path d="M 133 84 L 124 89 L 133 94" strokeWidth="3.4" />
            {state === "error" ? (
              <path d="M 105 95 Q 110 90 115 95" strokeWidth="3.4" />
            ) : (
              <path d="M 105 91 Q 110 96 115 91" strokeWidth="3.4" />
            )}
          </g>
        )}

        {/* Belly 'x' Stitch */}
        <g stroke="#786588" strokeWidth="3.4" strokeLinecap="round">
          <line x1="106" y1="152" x2="114" y2="160" />
          <line x1="114" y1="152" x2="106" y2="160" />
        </g>

        {/* Drink Cup + Two-Tone Straw + Right Arm */}
        <g
          transform={
            isSipping
              ? "translate(18, -14) rotate(12 72 124)"
              : "translate(0, 0)"
          }
        >
          {/* Two-Tone Bent Straw */}
          <path
            d="M 59 110 L 59 92 L 72 80"
            fill="none"
            stroke="#8B7798"
            strokeWidth="6.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M 61 110 L 61 93 L 73 81"
            fill="none"
            stroke="#C4D758"
            strokeWidth="4.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {/* Tapered Cup Body */}
          <polygon points="44,114 78,114 73,154 49,154" fill="#B8CB4E" />
          {/* Purple Collar Ring */}
          <rect x="41" y="112" width="40" height="5.5" rx="2.8" fill="#8B7798" />
          {/* Lime Cup Lid */}
          <rect x="42" y="106" width="38" height="6.5" rx="3.2" fill="#C4D758" />
          {/* Right Arm Paw Cradling Cup */}
          <ellipse cx="47" cy="134" rx="14" ry="12" fill="#C0D354" />
        </g>

        {/* Bounce Motion Lines on Executing */}
        {state === "executing" && (
          <g stroke="#786588" strokeWidth="3" strokeLinecap="round" fill="none">
            <path d="M 152 176 Q 158 178 163 172" />
            <path d="M 165 172 Q 171 174 176 168" />
          </g>
        )}
      </svg>
    </button>
  );
};

export const RobotMascot3D: React.FC<RobotMascot3DProps> = ({
  state,
  audioLevel,
  theme = "dark",
  compact = false,
  onClick,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [webglFailed, setWebglFailed] = useState(false);

  const stateRef = useRef<MascotState>(state);
  const audioRef = useRef<number>(audioLevel);
  const themeRef = useRef<"dark" | "light">(theme);
  const onClickRef = useRef<(() => void) | undefined>(onClick);
  const clickImpulseRef = useRef<number>(0);
  const clickCycleIdxRef = useRef<number>(0);
  const playfulOverrideRef = useRef<MascotPoseVariant | null>(null);
  const playfulTimerRef = useRef<number>(0);

  stateRef.current = state;
  audioRef.current = audioLevel;
  themeRef.current = theme;
  onClickRef.current = onClick;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let renderer: THREE.WebGLRenderer | null = null;
    try {
      renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
        powerPreference: "high-performance",
      });
    } catch {
      setWebglFailed(true);
      return;
    }

    if (!renderer.getContext()) {
      renderer.dispose();
      setWebglFailed(true);
      return;
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(
      container.clientWidth || 240,
      container.clientHeight || 220
    );
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      30,
      (container.clientWidth || 240) / (container.clientHeight || 220),
      0.1,
      50
    );
    camera.position.set(0, 0.36, 5.45);
    camera.lookAt(0, 0.06, 0);

    const { pmremGenerator, envTarget, rimLight } = setupMascotStudioLighting(
      scene,
      renderer,
      RoomEnvironment
    );

    const rig = createMascotRig();
    scene.add(rig.root);

    // Mouse pointer tracking
    let targetMouseX = 0;
    let targetMouseY = 0;
    let currentMouseX = 0;
    let currentMouseY = 0;

    const handlePointerMove = (e: PointerEvent) => {
      const nx = (e.clientX / window.innerWidth) * 2 - 1;
      const ny = -(e.clientY / window.innerHeight) * 2 + 1;
      targetMouseX = THREE.MathUtils.clamp(nx, -1, 1);
      targetMouseY = THREE.MathUtils.clamp(ny, -1, 1);
    };
    window.addEventListener("pointermove", handlePointerMove, { passive: true });

    const handleCanvasClick = () => {
      clickImpulseRef.current = 1.0;
      const nextPose =
        CLICK_PLAYFUL_CYCLE[
          clickCycleIdxRef.current % CLICK_PLAYFUL_CYCLE.length
        ];
      clickCycleIdxRef.current += 1;
      playfulOverrideRef.current = nextPose;
      playfulTimerRef.current = 1.65;
      onClickRef.current?.();
    };
    renderer.domElement.addEventListener("click", handleCanvasClick);

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0 && renderer) {
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
          renderer.setSize(width, height);
        }
      }
    });
    resizeObserver.observe(container);

    const clock = new THREE.Clock();
    const baseRimColor = new THREE.Color(0xe4d0ff);
    const errorRimColor = new THREE.Color(0xf9a8d4);
    let rafId = 0;

    const animate = () => {
      rafId = requestAnimationFrame(animate);
      const dt = Math.min(clock.getDelta(), 0.05);
      const t = clock.getElapsedTime();

      currentMouseX += (targetMouseX - currentMouseX) * Math.min(1, dt * 5);
      currentMouseY += (targetMouseY - currentMouseY) * Math.min(1, dt * 5);

      if (clickImpulseRef.current > 0.001) {
        clickImpulseRef.current = Math.max(
          0,
          clickImpulseRef.current - dt * 1.9
        );
      }

      if (playfulTimerRef.current > 0) {
        playfulTimerRef.current = Math.max(0, playfulTimerRef.current - dt);
        if (playfulTimerRef.current === 0) {
          playfulOverrideRef.current = null;
        }
      }

      // Subtle rose rim tint in error state without breaking clay aesthetic
      rimLight.color.lerp(
        stateRef.current === "error" ? errorRimColor : baseRimColor,
        Math.min(1, dt * 5)
      );

      rig.updateAnimation({
        state: stateRef.current,
        audioLevel: audioRef.current,
        time: t,
        dt,
        pointerX: currentMouseX,
        pointerY: currentMouseY,
        clickImpulse: clickImpulseRef.current,
        playfulOverride: playfulOverrideRef.current,
      });

      renderer!.render(scene, camera);
    };

    animate();

    return () => {
      cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      window.removeEventListener("pointermove", handlePointerMove);
      if (renderer) {
        renderer.domElement.removeEventListener("click", handleCanvasClick);
        renderer.dispose();
      }
      envTarget.dispose();
      pmremGenerator.dispose();
      rig.dispose();
    };
  }, []);

  if (webglFailed) {
    return (
      <SvgFallbackMascot
        state={state}
        audioLevel={audioLevel}
        compact={compact}
        onClick={onClick}
      />
    );
  }

  return (
    <div
      ref={containerRef}
      title="Click Mochi companion"
      className="w-full h-full cursor-pointer select-none"
    />
  );
};
