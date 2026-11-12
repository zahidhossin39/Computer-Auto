import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import type { MascotState } from "../types";

interface RobotMascot3DProps {
  state: MascotState;
  audioLevel: number;
  theme?: "dark" | "light";
  compact?: boolean;
  onClick?: () => void;
}

const STATE_COLORS: Record<MascotState, string> = {
  ready: "#38bdf8",
  listening: "#34d399",
  processing: "#a855f7",
  executing: "#a855f7",
  guardrail: "#f59e0b",
  error: "#f43f5e",
};

const SvgFallbackMascot: React.FC<{
  state: MascotState;
  audioLevel: number;
  compact?: boolean;
  onClick?: () => void;
}> = ({ state, audioLevel, compact, onClick }) => {
  const accent = STATE_COLORS[state] || "#38bdf8";
  const scale = 1 + (state === "listening" ? audioLevel * 0.08 : 0);

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Nova AI Companion"
      className="relative flex items-center justify-center w-full h-full cursor-pointer focus:outline-none group"
    >
      <div
        className="absolute rounded-full blur-2xl opacity-30 transition-all duration-300"
        style={{
          width: compact ? 80 : 150,
          height: compact ? 80 : 150,
          background: accent,
          transform: `scale(${scale})`,
        }}
      />
      <svg
        viewBox="0 0 180 180"
        className="animate-float drop-shadow-2xl transition-transform duration-300 group-hover:scale-105"
        style={{ width: compact ? 92 : 168, height: compact ? 92 : 168 }}
      >
        {/* Orbital ring */}
        <ellipse
          cx="90"
          cy="104"
          rx="68"
          ry="18"
          fill="none"
          stroke={accent}
          strokeWidth="2.5"
          strokeDasharray="10 6"
          opacity="0.7"
        />
        {/* Antenna */}
        <line x1="90" y1="30" x2="90" y2="16" stroke="#94a3b8" strokeWidth="3" strokeLinecap="round" />
        <circle cx="90" cy="13" r="6" fill={accent} />
        {/* Head */}
        <rect x="44" y="30" width="92" height="68" rx="30" fill="#e2e8f0" stroke="#cbd5e1" strokeWidth="2" />
        {/* Visor */}
        <rect x="53" y="42" width="74" height="42" rx="18" fill="#090d16" />
        {/* Eyes */}
        <ellipse cx="73" cy="60" rx="7" ry={state === "error" ? 3 : 8} fill={accent} />
        <ellipse cx="107" cy="60" rx="7" ry={state === "error" ? 3 : 8} fill={accent} />
        {/* Voice bar */}
        <rect
          x="77"
          y="73"
          width="26"
          height={3 + audioLevel * 5}
          rx="2"
          fill={accent}
          opacity="0.9"
        />
        {/* Body */}
        <rect x="60" y="104" width="60" height="44" rx="22" fill="#cbd5e1" />
        <circle cx="90" cy="126" r="10" fill={accent} />
        {/* Floating Paws */}
        <circle cx="42" cy="122" r="10" fill="#e2e8f0" />
        <circle cx="138" cy="122" r="10" fill="#e2e8f0" />
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
  const clickSpinRef = useRef<number>(0);

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
    renderer.setSize(container.clientWidth || 240, container.clientHeight || 220);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      36,
      (container.clientWidth || 240) / (container.clientHeight || 220),
      0.1,
      100
    );
    camera.position.set(0, 0.2, 6.2);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.9);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0xffffff, 1.8);
    keyLight.position.set(3, 5, 4);
    scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight(0x38bdf8, 1.4);
    rimLight.position.set(-4, 2, -3);
    scene.add(rimLight);

    const accentPointLight = new THREE.PointLight(0x38bdf8, 2.2, 8);
    accentPointLight.position.set(0, 0.2, 1.8);
    scene.add(accentPointLight);

    // Materials
    const ceramicMat = new THREE.MeshPhysicalMaterial({
      color: 0xf1f5f9,
      metalness: 0.14,
      roughness: 0.18,
      clearcoat: 1.0,
      clearcoatRoughness: 0.1,
    });

    const trimMat = new THREE.MeshStandardMaterial({
      color: 0x334155,
      metalness: 0.65,
      roughness: 0.3,
    });

    const visorMat = new THREE.MeshPhysicalMaterial({
      color: 0x050811,
      metalness: 0.25,
      roughness: 0.08,
      clearcoat: 1.0,
      clearcoatRoughness: 0.04,
    });

    const glowMat = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      emissive: 0x38bdf8,
      emissiveIntensity: 2.0,
      roughness: 0.2,
      metalness: 0.1,
    });

    const ringMat = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      emissive: 0x38bdf8,
      emissiveIntensity: 1.4,
      transparent: true,
      opacity: 0.85,
      roughness: 0.2,
    });

    const shieldMat = new THREE.MeshStandardMaterial({
      color: 0xf59e0b,
      emissive: 0xf59e0b,
      emissiveIntensity: 1.5,
      transparent: true,
      opacity: 0,
      side: THREE.DoubleSide,
    });

    // Root mascot group
    const novaGroup = new THREE.Group();
    scene.add(novaGroup);

    // Head group
    const headGroup = new THREE.Group();
    headGroup.position.set(0, 0.65, 0);
    novaGroup.add(headGroup);

    // Rounded ceramic head (slightly squashed sphere)
    const headGeo = new THREE.SphereGeometry(0.92, 48, 36);
    headGeo.scale(1.12, 0.92, 0.96);
    const headMesh = new THREE.Mesh(headGeo, ceramicMat);
    headGroup.add(headMesh);

    // Visor
    const visorGeo = new THREE.SphereGeometry(0.84, 42, 32);
    visorGeo.scale(1.04, 0.72, 0.78);
    const visorMesh = new THREE.Mesh(visorGeo, visorMat);
    visorMesh.position.set(0, -0.02, 0.27);
    headGroup.add(visorMesh);

    // Left & Right Ear Pods
    const earGeo = new THREE.CylinderGeometry(0.24, 0.24, 0.18, 24);
    earGeo.rotateZ(Math.PI / 2);
    const leftEar = new THREE.Mesh(earGeo, trimMat);
    leftEar.position.set(-1.05, 0, 0);
    headGroup.add(leftEar);

    const rightEar = new THREE.Mesh(earGeo, trimMat);
    rightEar.position.set(1.05, 0, 0);
    headGroup.add(rightEar);

    const earRingGeo = new THREE.TorusGeometry(0.18, 0.03, 12, 24);
    earRingGeo.rotateY(Math.PI / 2);
    const leftEarRing = new THREE.Mesh(earRingGeo, glowMat);
    leftEarRing.position.set(-1.14, 0, 0);
    headGroup.add(leftEarRing);

    const rightEarRing = new THREE.Mesh(earRingGeo, glowMat);
    rightEarRing.position.set(1.14, 0, 0);
    headGroup.add(rightEarRing);

    // Eyes (expressive LED capsules)
    const eyeGeo = new THREE.CapsuleGeometry(0.11, 0.14, 8, 16);
    const leftEye = new THREE.Mesh(eyeGeo, glowMat);
    leftEye.position.set(-0.32, 0.08, 0.88);
    headGroup.add(leftEye);

    const rightEye = new THREE.Mesh(eyeGeo, glowMat);
    rightEye.position.set(0.32, 0.08, 0.88);
    headGroup.add(rightEye);

    // Mouth / Voice equalizer bar
    const mouthGeo = new THREE.CapsuleGeometry(0.035, 0.22, 6, 12);
    mouthGeo.rotateZ(Math.PI / 2);
    const mouthBar = new THREE.Mesh(mouthGeo, glowMat);
    mouthBar.position.set(0, -0.2, 0.89);
    headGroup.add(mouthBar);

    // Scanner beam (for processing/executing)
    const scanGeo = new THREE.BoxGeometry(1.1, 0.04, 0.05);
    const scanMat = new THREE.MeshBasicMaterial({
      color: 0xa855f7,
      transparent: true,
      opacity: 0,
    });
    const scanBeam = new THREE.Mesh(scanGeo, scanMat);
    scanBeam.position.set(0, 0, 0.94);
    headGroup.add(scanBeam);

    // Antenna
    const stalkGeo = new THREE.CylinderGeometry(0.035, 0.05, 0.42, 12);
    const stalk = new THREE.Mesh(stalkGeo, trimMat);
    stalk.position.set(0, 0.98, -0.05);
    headGroup.add(stalk);

    const orbGeo = new THREE.SphereGeometry(0.14, 24, 24);
    const antennaOrb = new THREE.Mesh(orbGeo, glowMat);
    antennaOrb.position.set(0, 1.24, -0.05);
    headGroup.add(antennaOrb);

    // Body group
    const bodyGroup = new THREE.Group();
    bodyGroup.position.set(0, -0.58, 0);
    novaGroup.add(bodyGroup);

    const torsoGeo = new THREE.CapsuleGeometry(0.46, 0.42, 16, 32);
    const torsoMesh = new THREE.Mesh(torsoGeo, ceramicMat);
    bodyGroup.add(torsoMesh);

    const coreGeo = new THREE.SphereGeometry(0.22, 24, 24);
    const coreMesh = new THREE.Mesh(coreGeo, glowMat);
    coreMesh.position.set(0, 0.04, 0.36);
    bodyGroup.add(coreMesh);

    const coreRingGeo = new THREE.TorusGeometry(0.26, 0.028, 12, 32);
    const coreRing = new THREE.Mesh(coreRingGeo, trimMat);
    coreRing.position.set(0, 0.04, 0.38);
    bodyGroup.add(coreRing);

    // Floating magnetic paws/hands
    const handGeo = new THREE.SphereGeometry(0.19, 24, 24);
    handGeo.scale(0.95, 1.25, 0.85);
    const leftHand = new THREE.Mesh(handGeo, ceramicMat);
    leftHand.position.set(-0.88, -0.45, 0.18);
    novaGroup.add(leftHand);

    const rightHand = new THREE.Mesh(handGeo, ceramicMat);
    rightHand.position.set(0.88, -0.45, 0.18);
    novaGroup.add(rightHand);

    // Orbital energy rings
    const orbitalGeo1 = new THREE.TorusGeometry(1.58, 0.025, 12, 72);
    const orbitalRing1 = new THREE.Mesh(orbitalGeo1, ringMat);
    orbitalRing1.rotation.x = Math.PI / 2.3;
    orbitalRing1.rotation.y = 0.25;
    novaGroup.add(orbitalRing1);

    const orbitalGeo2 = new THREE.TorusGeometry(1.75, 0.018, 10, 72);
    const orbitalRing2 = new THREE.Mesh(orbitalGeo2, ringMat);
    orbitalRing2.rotation.x = -Math.PI / 2.6;
    orbitalRing2.rotation.y = -0.35;
    novaGroup.add(orbitalRing2);

    // Soundwave ring (expands with audioLevel when listening)
    const soundWaveGeo = new THREE.RingGeometry(1.15, 1.22, 48);
    const soundWaveMat = new THREE.MeshBasicMaterial({
      color: 0x34d399,
      transparent: true,
      opacity: 0,
      side: THREE.DoubleSide,
    });
    const soundWaveRing = new THREE.Mesh(soundWaveGeo, soundWaveMat);
    soundWaveRing.position.set(0, 0.3, -0.4);
    novaGroup.add(soundWaveRing);

    // Guardrail protective shield
    const shieldGeo = new THREE.RingGeometry(0.95, 1.15, 6);
    const shieldRing = new THREE.Mesh(shieldGeo, shieldMat);
    shieldRing.position.set(0, 0.15, 1.35);
    novaGroup.add(shieldRing);

    // Floating star / data particles
    const particleCount = 36;
    const particlePositions = new Float32Array(particleCount * 3);
    const particleAngles: number[] = [];
    const particleRadii: number[] = [];
    const particleHeights: number[] = [];

    for (let i = 0; i < particleCount; i++) {
      const angle = (i / particleCount) * Math.PI * 2;
      const radius = 1.5 + (i % 5) * 0.25;
      const y = ((i % 7) - 3) * 0.38;
      particleAngles.push(angle);
      particleRadii.push(radius);
      particleHeights.push(y);
      particlePositions[i * 3] = Math.cos(angle) * radius;
      particlePositions[i * 3 + 1] = y;
      particlePositions[i * 3 + 2] = Math.sin(angle) * radius;
    }

    const particleGeo = new THREE.BufferGeometry();
    particleGeo.setAttribute(
      "position",
      new THREE.BufferAttribute(particlePositions, 3)
    );
    const particleMat = new THREE.PointsMaterial({
      color: 0x38bdf8,
      size: 0.06,
      transparent: true,
      opacity: 0.75,
    });
    const particles = new THREE.Points(particleGeo, particleMat);
    scene.add(particles);

    // Mouse tracking
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
      clickSpinRef.current = 1.0;
      onClickRef.current?.();
    };
    renderer.domElement.addEventListener("click", handleCanvasClick);

    // Resize handling
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

    // Animation loop
    const clock = new THREE.Clock();
    const targetColor = new THREE.Color(STATE_COLORS.ready);
    const currentColor = new THREE.Color(STATE_COLORS.ready);
    let nextBlinkTime = 2.5;
    let rafId = 0;

    const animate = () => {
      rafId = requestAnimationFrame(animate);
      const dt = Math.min(clock.getDelta(), 0.05);
      const t = clock.getElapsedTime();

      const st = stateRef.current;
      const level = THREE.MathUtils.clamp(audioRef.current, 0, 1);

      // Theme ceramic brightness adjustment
      ceramicMat.color.setHex(themeRef.current === "dark" ? 0xf1f5f9 : 0xe2e8f0);

      // Smooth state color transition
      targetColor.set(STATE_COLORS[st] || STATE_COLORS.ready);
      currentColor.lerp(targetColor, Math.min(1, dt * 6));
      glowMat.color.copy(currentColor);
      glowMat.emissive.copy(currentColor);
      ringMat.color.copy(currentColor);
      ringMat.emissive.copy(currentColor);
      rimLight.color.copy(currentColor);
      accentPointLight.color.copy(currentColor);
      particleMat.color.copy(currentColor);

      // Mouse smoothing
      currentMouseX += (targetMouseX - currentMouseX) * Math.min(1, dt * 5);
      currentMouseY += (targetMouseY - currentMouseY) * Math.min(1, dt * 5);

      // Click happy spin decay
      let spinOffset = 0;
      let waveBoost = 0;
      if (clickSpinRef.current > 0.001) {
        clickSpinRef.current = Math.max(0, clickSpinRef.current - dt * 1.8);
        const p = 1 - clickSpinRef.current;
        spinOffset = Math.sin(p * Math.PI) * Math.PI * 2;
        waveBoost = Math.sin(p * Math.PI * 4) * 0.35;
      }

      // Base hover bob
      const bobSpeed = st === "processing" || st === "executing" ? 3.2 : 1.9;
      const bobAmp = st === "listening" ? 0.06 : 0.09;
      novaGroup.position.y = Math.sin(t * bobSpeed) * bobAmp;

      // Attentive lean & error tilt
      let targetRotX = -currentMouseY * 0.22;
      let targetRotZ = 0;
      if (st === "listening") {
        targetRotX += 0.14;
      } else if (st === "error") {
        targetRotZ = Math.sin(t * 2.5) * 0.08 - 0.16;
      }

      novaGroup.rotation.y = currentMouseX * 0.28 + spinOffset;
      headGroup.rotation.y = currentMouseX * 0.32;
      headGroup.rotation.x = THREE.MathUtils.lerp(
        headGroup.rotation.x,
        targetRotX,
        dt * 6
      );
      headGroup.rotation.z = THREE.MathUtils.lerp(
        headGroup.rotation.z,
        targetRotZ,
        dt * 6
      );

      // Blinking
      let eyeScaleY = 1.0;
      if (t > nextBlinkTime) {
        const blinkProgress = (t - nextBlinkTime) / 0.16;
        if (blinkProgress < 1) {
          eyeScaleY = Math.max(0.08, Math.abs(Math.cos(blinkProgress * Math.PI)));
        } else {
          nextBlinkTime = t + 2.8 + Math.random() * 2.8;
        }
      }
      if (clickSpinRef.current > 0.2) {
        eyeScaleY = 0.25; // happy squint
      } else if (st === "error") {
        eyeScaleY = 0.45;
      }
      leftEye.scale.set(1, eyeScaleY, 1);
      rightEye.scale.set(1, eyeScaleY, 1);

      // Mouth / Voice Bar & Antenna Orb Audio Reactivity
      const voiceScale = st === "listening" ? 1 + level * 2.2 : st === "processing" || st === "executing" ? 1.2 + Math.sin(t * 14) * 0.35 : 1;
      mouthBar.scale.set(1 + level * 0.35, voiceScale, 1);

      const orbScale = 1 + (st === "listening" ? level * 0.55 : Math.sin(t * 3) * 0.08);
      antennaOrb.scale.setScalar(orbScale);
      glowMat.emissiveIntensity =
        st === "listening"
          ? 2.0 + level * 2.5
          : st === "processing" || st === "executing"
          ? 2.6 + Math.sin(t * 10) * 0.6
          : 1.8;

      // Hands animation
      if (st === "guardrail") {
        leftHand.position.y = THREE.MathUtils.lerp(leftHand.position.y, 0.22, dt * 7);
        rightHand.position.y = THREE.MathUtils.lerp(rightHand.position.y, 0.22, dt * 7);
        leftHand.position.z = THREE.MathUtils.lerp(leftHand.position.z, 0.65, dt * 7);
        rightHand.position.z = THREE.MathUtils.lerp(rightHand.position.z, 0.65, dt * 7);
      } else {
        const handBob = Math.sin(t * 2.4 + 0.8) * 0.08;
        leftHand.position.y = THREE.MathUtils.lerp(
          leftHand.position.y,
          -0.45 + handBob,
          dt * 6
        );
        rightHand.position.y = THREE.MathUtils.lerp(
          rightHand.position.y,
          -0.45 - handBob + Math.abs(waveBoost),
          dt * 6
        );
        leftHand.position.z = THREE.MathUtils.lerp(leftHand.position.z, 0.18, dt * 6);
        rightHand.position.z = THREE.MathUtils.lerp(rightHand.position.z, 0.18, dt * 6);
      }

      // Orbital rings
      const ringSpeed =
        st === "processing" || st === "executing"
          ? 3.8
          : st === "listening"
          ? 1.6 + level * 2.0
          : 0.65;
      orbitalRing1.rotation.z += dt * ringSpeed;
      orbitalRing2.rotation.z -= dt * ringSpeed * 0.8;
      if (st === "processing" || st === "executing") {
        orbitalRing2.rotation.x = -Math.PI / 2.6 + Math.sin(t * 3) * 0.45;
        scanMat.opacity = 0.75;
        scanBeam.position.y = Math.sin(t * 7) * 0.22;
      } else {
        orbitalRing2.rotation.x = THREE.MathUtils.lerp(
          orbitalRing2.rotation.x,
          -Math.PI / 2.6,
          dt * 4
        );
        scanMat.opacity = THREE.MathUtils.lerp(scanMat.opacity, 0, dt * 8);
      }

      // Soundwave ring when listening
      if (st === "listening") {
        const waveScale = 1 + ((t * 1.4) % 1) * (0.45 + level * 0.7);
        soundWaveRing.scale.setScalar(waveScale);
        soundWaveMat.opacity = (1 - ((t * 1.4) % 1)) * (0.3 + level * 0.55);
      } else {
        soundWaveMat.opacity = THREE.MathUtils.lerp(soundWaveMat.opacity, 0, dt * 8);
      }

      // Guardrail shield
      if (st === "guardrail") {
        shieldMat.opacity = THREE.MathUtils.lerp(shieldMat.opacity, 0.68, dt * 6);
        shieldRing.rotation.z += dt * 1.2;
      } else {
        shieldMat.opacity = THREE.MathUtils.lerp(shieldMat.opacity, 0, dt * 8);
      }

      // Orbit particles
      const posAttr = particleGeo.getAttribute("position") as THREE.BufferAttribute;
      const pSpeed = st === "processing" || st === "executing" ? 1.4 : 0.35;
      for (let i = 0; i < particleCount; i++) {
        particleAngles[i] += dt * pSpeed * (i % 2 === 0 ? 1 : -0.7);
        const r = particleRadii[i];
        posAttr.setXYZ(
          i,
          Math.cos(particleAngles[i]) * r,
          particleHeights[i] + Math.sin(t * 1.5 + i) * 0.08,
          Math.sin(particleAngles[i]) * r
        );
      }
      posAttr.needsUpdate = true;

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
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.Points) {
          obj.geometry.dispose();
          if (Array.isArray(obj.material)) {
            obj.material.forEach((m) => m.dispose());
          } else {
            obj.material.dispose();
          }
        }
      });
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
      title="Click Nova to toggle microphone"
      className="w-full h-full cursor-pointer select-none"
    />
  );
};
