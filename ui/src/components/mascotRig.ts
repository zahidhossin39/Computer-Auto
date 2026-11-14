import * as THREE from "three";
import { mergeVertices } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { MascotState } from "../types";

export type MascotPoseVariant = MascotState | "happy_sip";

export interface MascotRigHandles {
  root: THREE.Group;
  floatGroup: THREE.Group;
  bodyMesh: THREE.Mesh;
  capGroup: THREE.Group;
  leftArmGroup: THREE.Group;
  rightArmHoldGroup: THREE.Group;
  cupGroup: THREE.Group;
  faceGroup: THREE.Group;
  bounceLinesGroup: THREE.Group;
  floorShadowMesh: THREE.Mesh;
  expressions: {
    pillEyes: THREE.Group;
    closedDownEyes: THREE.Group;
    happyArchEyes: THREE.Group;
    squintChevronEyes: THREE.Group;
    smileMouth: THREE.Group;
    puckerMouth: THREE.Group;
    sipMouth: THREE.Group;
    worryMouth: THREE.Group;
  };
  materials: {
    bodyMat: THREE.MeshPhysicalMaterial;
    limeMat: THREE.MeshPhysicalMaterial;
    limeBrightMat: THREE.MeshPhysicalMaterial;
    purpleTrimMat: THREE.MeshPhysicalMaterial;
    plumFeatureMat: THREE.MeshPhysicalMaterial;
    freckleMat: THREE.MeshPhysicalMaterial;
    capInnerMat: THREE.MeshStandardMaterial;
  };
  setPoseSnapshot: (
    variant: MascotPoseVariant,
    options?: {
      yaw?: number;
      pitch?: number;
      time?: number;
      showShadow?: boolean;
    }
  ) => void;
  updateAnimation: (params: {
    state: MascotState;
    audioLevel: number;
    time: number;
    dt: number;
    pointerX: number;
    pointerY: number;
    clickImpulse: number;
    playfulOverride?: MascotPoseVariant | null;
  }) => void;
  dispose: () => void;
}

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = THREE.MathUtils.clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}

/**
 * Computes the exact surface Z on the front face window at a given (x, y)
 * so facial features sit flush on the recessed inner face pillow.
 */
export function getInnerFaceZ(x: number, y: number): number {
  const dy = y - 0.215;
  return (
    0.768 +
    0.068 *
      Math.max(
        0,
        1 -
          0.6 * ((x * x) / (0.435 * 0.435)) -
          0.6 * ((dy * dy) / (0.258 * 0.258))
      )
  );
}

/**
 * Builds the seamless closed plump egg-mochi body with an analytical C2-smooth
 * recessed stadium face hood, subtle rolled clay rim, and rich vertex colors.
 */
function buildSculptedBodyGeometry(): THREE.BufferGeometry {
  const rawBox = new THREE.BoxGeometry(1, 1, 1, 68, 68, 68);
  rawBox.deleteAttribute("uv");
  const geo = mergeVertices(rawBox, 1e-4);
  rawBox.dispose();

  const pos = geo.getAttribute("position") as THREE.BufferAttribute;
  const count = pos.count;
  const colors = new Float32Array(count * 3);

  const colBodyBase = new THREE.Color(0xb5ca4a);
  const colBodyTop = new THREE.Color(0xbed252);
  const colBodyBottom = new THREE.Color(0x96aa36);
  const colCreaseAO = new THREE.Color(0x8e9f3f);
  const colInnerFace = new THREE.Color(0xdbe392);
  const colInnerCenter = new THREE.Color(0xe1e99b);
  const tmpColor = new THREE.Color();
  const tmpOuter = new THREE.Color();
  const tmpInner = new THREE.Color();

  const faceCy = 0.215;
  const faceHx = 0.435;
  const faceHy = 0.258;
  const segHalfX = faceHx - faceHy;
  const stadiumR = faceHy;

  for (let i = 0; i < count; i++) {
    const vx = pos.getX(i);
    const vy = pos.getY(i);
    const vz = pos.getZ(i);

    const len = Math.hypot(vx, vy, vz) || 1;
    const nx = vx / len;
    const ny = vy / len;
    const nz = vz / len;

    const yNorm = ny;
    const rx =
      0.905 -
      0.068 * yNorm +
      0.015 * Math.cos(yNorm * Math.PI * 0.5);

    const ry = 0.935;
    const rz = rx * 0.955;

    let x = nx * rx;
    let y = ny * ry - 0.024 * (1 - ny * ny);
    let z = nz * rz;

    if (nz < 0) {
      const backWeight = Math.max(
        0,
        1 - Math.pow((yNorm + 0.12) / 0.82, 2)
      );
      z -= 0.038 * (-nz) * backWeight;
    }

    if (nz > 0) {
      const frontWeight = Math.max(
        0,
        1 - Math.pow((yNorm - 0.2) / 0.62, 2)
      );
      z -= 0.018 * nz * frontWeight;
    }

    let dist = 1.0;
    if (nz > 0.15) {
      const dx = Math.max(Math.abs(x) - segHalfX, 0);
      const dy = y - faceCy;
      dist = Math.hypot(dx, dy) - stadiumR;

      const lipT = Math.max(0, 1 - Math.pow((dist - 0.02) / 0.045, 2));
      const lipBump = 0.006 * lipT * lipT * smoothstep(0.15, 0.45, nz);

      const s = smoothstep(-0.032, 0.014, dist);
      const innerZ = getInnerFaceZ(x, y);

      z = THREE.MathUtils.lerp(innerZ, z + lipBump, s);

      const rimWall = Math.sin(s * Math.PI);
      if (rimWall > 0.001) {
        const radLen = Math.hypot(x, y - faceCy) || 1;
        x += (x / radLen) * 0.005 * rimWall;
        y += ((y - faceCy) / radLen) * 0.005 * rimWall;
      }
    }

    pos.setXYZ(i, x, y, z);

    const verticalGrad = THREE.MathUtils.clamp((ny + 1) * 0.5, 0, 1);
    if (verticalGrad > 0.48) {
      tmpOuter.lerpColors(
        colBodyBase,
        colBodyTop,
        (verticalGrad - 0.48) / 0.52
      );
    } else {
      tmpOuter.lerpColors(colBodyBottom, colBodyBase, verticalGrad / 0.48);
    }

    if (nz > 0.15 && dist < 0.05) {
      const dy = y - faceCy;
      const centerFactor = THREE.MathUtils.clamp(
        1 - Math.hypot(x / faceHx, dy / faceHy),
        0,
        1
      );
      tmpInner.lerpColors(colInnerFace, colInnerCenter, centerFactor * 0.45);

      const sColor = smoothstep(-0.028, 0.008, dist);
      tmpColor.lerpColors(tmpInner, tmpOuter, sColor);

      const creaseBand = Math.exp(-Math.pow((dist + 0.013) / 0.016, 2));
      const topSideBias = THREE.MathUtils.clamp(
        0.65 + 0.35 * (dy / faceHy),
        0.38,
        1.0
      );
      tmpColor.lerp(colCreaseAO, creaseBand * 0.62 * topSideBias);
    } else {
      tmpColor.copy(tmpOuter);
    }

    colors[i * 3] = tmpColor.r;
    colors[i * 3 + 1] = tmpColor.g;
    colors[i * 3 + 2] = tmpColor.b;
  }

  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geo.computeVertexNormals();
  return geo;
}

/**
 * Builds a twist-free variable-radius capsule curve using Parallel Transport (Bishop) frames
 * and explicit outward analytical normals so limbs never twist or invert shading.
 */
function buildTaperedCapsuleCurve(
  points: THREE.Vector3[],
  radiusFn: (t: number) => number,
  tubularSegments = 36,
  radialSegments = 24,
  scaleX = 1.0,
  scaleZ = 1.0
): THREE.BufferGeometry {
  const curve = new THREE.CatmullRomCurve3(points);

  const tangents: THREE.Vector3[] = [];
  const normals: THREE.Vector3[] = [];
  const binormals: THREE.Vector3[] = [];

  for (let i = 0; i <= tubularSegments; i++) {
    tangents.push(curve.getTangentAt(i / tubularSegments).normalize());
  }

  const t0 = tangents[0];
  const ref =
    Math.abs(t0.y) < 0.9
      ? new THREE.Vector3(0, 1, 0)
      : new THREE.Vector3(1, 0, 0);
  const b0 = new THREE.Vector3().crossVectors(t0, ref).normalize();
  const n0 = new THREE.Vector3().crossVectors(b0, t0).normalize();
  normals.push(n0);
  binormals.push(b0);

  const q = new THREE.Quaternion();
  for (let i = 1; i <= tubularSegments; i++) {
    q.setFromUnitVectors(tangents[i - 1], tangents[i]);
    const ni = normals[i - 1].clone().applyQuaternion(q);
    ni.addScaledVector(tangents[i], -ni.dot(tangents[i])).normalize();
    const bi = new THREE.Vector3().crossVectors(tangents[i], ni).normalize();
    normals.push(ni);
    binormals.push(bi);
  }

  const ringCount = tubularSegments + 1;
  const capRings = 8;
  const totalRings = capRings + ringCount + capRings;

  const positions: number[] = [];
  const outNormals: number[] = [];
  const indices: number[] = [];

  const p = new THREE.Vector3();
  const vertex = new THREE.Vector3();
  const vNorm = new THREE.Vector3();

  const pushRing = (
    center: THREE.Vector3,
    N: THREE.Vector3,
    B: THREE.Vector3,
    T: THREE.Vector3,
    r: number,
    axialOffset: number,
    axialNormSign: number,
    radialNormWeight: number
  ) => {
    for (let j = 0; j <= radialSegments; j++) {
      const v = (j / radialSegments) * Math.PI * 2;
      const cos = Math.cos(v);
      const sin = Math.sin(v);
      vertex
        .copy(center)
        .addScaledVector(T, axialOffset)
        .addScaledVector(N, cos * r * scaleX)
        .addScaledVector(B, sin * r * scaleZ);
      positions.push(vertex.x, vertex.y, vertex.z);

      vNorm
        .set(0, 0, 0)
        .addScaledVector(N, (cos / scaleX) * radialNormWeight)
        .addScaledVector(B, (sin / scaleZ) * radialNormWeight)
        .addScaledVector(T, axialNormSign)
        .normalize();
      outNormals.push(vNorm.x, vNorm.y, vNorm.z);
    }
  };

  const p0 = curve.getPointAt(0);
  const r0 = radiusFn(0);
  for (let c = 0; c < capRings; c++) {
    const a = ((c / capRings) * Math.PI) / 2;
    const sinA = Math.sin(a);
    const cosA = Math.cos(a);
    pushRing(
      p0,
      normals[0],
      binormals[0],
      tangents[0],
      sinA * r0,
      -cosA * r0 * 0.85,
      -cosA,
      Math.max(0.01, sinA)
    );
  }

  for (let i = 0; i <= tubularSegments; i++) {
    const u = i / tubularSegments;
    curve.getPointAt(u, p);
    const r = radiusFn(u);
    pushRing(p, normals[i], binormals[i], tangents[i], r, 0, 0, 1.0);
  }

  const p1 = curve.getPointAt(1);
  const r1 = radiusFn(1);
  for (let c = 1; c <= capRings; c++) {
    const a = ((c / capRings) * Math.PI) / 2;
    const cosA = Math.cos(a);
    const sinA = Math.sin(a);
    pushRing(
      p1,
      normals[tubularSegments],
      binormals[tubularSegments],
      tangents[tubularSegments],
      cosA * r1,
      sinA * r1 * 0.85,
      sinA,
      Math.max(0.01, cosA)
    );
  }

  const stride = radialSegments + 1;
  for (let i = 0; i < totalRings - 1; i++) {
    for (let j = 0; j < radialSegments; j++) {
      const a = i * stride + j;
      const b = (i + 1) * stride + j;
      const c = (i + 1) * stride + (j + 1);
      const d = i * stride + (j + 1);
      indices.push(a, d, b);
      indices.push(b, d, c);
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geo.setAttribute("normal", new THREE.Float32BufferAttribute(outNormals, 3));
  geo.setIndex(indices);
  return geo;
}

/**
 * Builds the plump, smooth left bean arm from a closed manifold sphere
 * sculpted into a soft vertical teardrop hugging the +X flank.
 */
function buildSculptedLeftArmGeometry(): THREE.BufferGeometry {
  const geo = new THREE.SphereGeometry(1, 36, 28);
  const pos = geo.getAttribute("position") as THREE.BufferAttribute;

  for (let i = 0; i < pos.count; i++) {
    const nx = pos.getX(i);
    const ny = pos.getY(i);
    const nz = pos.getZ(i);

    const fullerPaw = 1.0 + 0.14 * Math.sin((ny - 0.15) * Math.PI * 0.5);
    const rx = 0.155 * fullerPaw;
    const ry = 0.255;
    const rz = 0.185 * fullerPaw;

    const t = (1 - ny) * 0.5;
    const curveX = 0.052 * Math.sin(t * Math.PI * 0.85);
    const curveZ = 0.024 * t;

    const x = nx * rx + curveX;
    const y = (ny - 0.65) * ry;
    const z = nz * rz + curveZ;

    pos.setXYZ(i, x, y, z);
  }

  geo.computeVertexNormals();
  return geo;
}

/**
 * Builds the 6-panel sideways baseball cap with:
 * - Rounded 6-panel dome terminating cleanly inside the bottom purple headband
 * - Rear D-shaped semicircular snapback cutout strictly ABOVE the uninterrupted bottom headband strap
 * - Shaded olive-green recessed inner pocket lining behind the cutout
 * - 6 meridian purple seams + lime top button (squatchee)
 * - Bright chartreuse-lime J-scooped upturned visor framed by purple perimeter piping (never self-shadowed muddy)
 */
function buildBaseballCap(materials: {
  limeMat: THREE.MeshPhysicalMaterial;
  limeBrightMat: THREE.MeshPhysicalMaterial;
  purpleTrimMat: THREE.MeshPhysicalMaterial;
  capInnerMat: THREE.MeshStandardMaterial;
}): THREE.Group {
  const capGroup = new THREE.Group();

  const R = 0.424;
  const H = 0.425;
  const cutHalfAngle = 0.42;
  const cutBaseV = 0.065;
  const cutTopV = 0.44;

  const domePoint = (
    theta: number,
    v: number,
    radialOffset = 0
  ): THREE.Vector3 => {
    const clampedV = Math.max(0, v);
    const elev = clampedV * (Math.PI * 0.5);
    const cosE = Math.cos(elev);
    const sinE = Math.sin(elev);
    const profileR = (R + radialOffset) * Math.pow(cosE, 0.78);
    const baseDip = -0.022 * (1 - clampedV) * Math.pow(Math.cos(theta), 2);
    const profileY = (H + radialOffset) * Math.pow(sinE, 0.86) + baseDip;
    return new THREE.Vector3(
      Math.sin(theta) * profileR,
      profileY,
      Math.cos(theta) * profileR
    );
  };

  // 1. Outer lime cap dome starting strictly at v = 0.0
  const nTheta = 96;
  const nV = 36;
  const domePositions: number[] = [];
  const domeIndices: number[] = [];

  for (let iv = 0; iv <= nV; iv++) {
    const v = iv / nV;
    for (let it = 0; it <= nTheta; it++) {
      const theta = (it / nTheta) * Math.PI * 2;
      const pt = domePoint(theta, v, 0);
      domePositions.push(pt.x, pt.y, pt.z);
    }
  }

  const stride = nTheta + 1;
  for (let iv = 0; iv < nV; iv++) {
    const vMid = (iv + 0.5) / nV;
    for (let it = 0; it < nTheta; it++) {
      const thetaMid = ((it + 0.5) / nTheta) * Math.PI * 2;
      const dBack = Math.atan2(
        Math.sin(thetaMid - Math.PI),
        Math.cos(thetaMid - Math.PI)
      );
      if (vMid >= cutBaseV) {
        const normU = dBack / cutHalfAngle;
        const normV = (vMid - cutBaseV) / (cutTopV - cutBaseV);
        if (normU * normU + normV * normV < 0.96) {
          continue;
        }
      }
      const a = iv * stride + it;
      const b = (iv + 1) * stride + it;
      const c = (iv + 1) * stride + (it + 1);
      const d = iv * stride + (it + 1);
      domeIndices.push(a, d, b);
      domeIndices.push(b, d, c);
    }
  }

  const domeGeo = new THREE.BufferGeometry();
  domeGeo.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(domePositions, 3)
  );
  domeGeo.setIndex(domeIndices);
  domeGeo.computeVertexNormals();

  const doubleSidedLime = materials.limeMat.clone();
  doubleSidedLime.side = THREE.DoubleSide;
  const domeMesh = new THREE.Mesh(domeGeo, doubleSidedLime);
  domeMesh.castShadow = true;
  domeMesh.receiveShadow = true;
  capGroup.add(domeMesh);

  // 2. Curved shaded dark-olive recessed inner pocket shell strictly above v = 0.035
  const pocketThetaSteps = 32;
  const pocketVSteps = 18;
  const pocketPos: number[] = [];
  const pocketIdx: number[] = [];
  for (let iv = 0; iv <= pocketVSteps; iv++) {
    const v = THREE.MathUtils.lerp(0.035, cutTopV + 0.1, iv / pocketVSteps);
    for (let it = 0; it <= pocketThetaSteps; it++) {
      const u = (it / pocketThetaSteps) * 2 - 1;
      const theta = Math.PI + u * (cutHalfAngle + 0.14);
      const depth = -0.02 - 0.032 * Math.cos(u * Math.PI * 0.5);
      const pt = domePoint(theta, v, depth);
      pocketPos.push(pt.x, pt.y, pt.z);
    }
  }
  const pStride = pocketThetaSteps + 1;
  for (let iv = 0; iv < pocketVSteps; iv++) {
    for (let it = 0; it < pocketThetaSteps; it++) {
      const a = iv * pStride + it;
      const b = (iv + 1) * pStride + it;
      const c = (iv + 1) * pStride + (it + 1);
      const d = iv * pStride + (it + 1);
      pocketIdx.push(a, d, b);
      pocketIdx.push(b, d, c);
    }
  }
  const pocketGeo = new THREE.BufferGeometry();
  pocketGeo.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(pocketPos, 3)
  );
  pocketGeo.setIndex(pocketIdx);
  pocketGeo.computeVertexNormals();
  const pocketMat = new THREE.MeshBasicMaterial({
    color: 0x485622,
    side: THREE.DoubleSide,
  });
  const pocketMesh = new THREE.Mesh(pocketGeo, pocketMat);
  capGroup.add(pocketMesh);

  // 3. Uninterrupted purple bottom headband ring
  const headbandPts: THREE.Vector3[] = [];
  const bandSteps = 72;
  for (let i = 0; i < bandSteps; i++) {
    const theta = (i / bandSteps) * Math.PI * 2;
    headbandPts.push(domePoint(theta, 0.015, 0.008));
  }
  const headbandCurve = new THREE.CatmullRomCurve3(headbandPts, true);
  const headbandGeo = new THREE.TubeGeometry(
    headbandCurve,
    96,
    0.024,
    16,
    true
  );
  const headbandMesh = new THREE.Mesh(headbandGeo, materials.purpleTrimMat);
  headbandMesh.castShadow = true;
  capGroup.add(headbandMesh);

  // 4. Raised purple semicircular arch border resting cleanly on top of the bottom headband strap
  const archPts: THREE.Vector3[] = [];
  const archSteps = 32;
  for (let i = 0; i <= archSteps; i++) {
    const angle = (i / archSteps) * Math.PI;
    const dTheta = Math.cos(angle) * cutHalfAngle;
    const v = 0.02 + Math.sin(angle) * (cutTopV - 0.02);
    archPts.push(domePoint(Math.PI + dTheta, v, 0.011));
  }
  const archCurve = new THREE.CatmullRomCurve3(archPts, false);
  const archGeo = new THREE.TubeGeometry(archCurve, 40, 0.022, 14, false);
  const archMesh = new THREE.Mesh(archGeo, materials.purpleTrimMat);
  archMesh.castShadow = true;
  capGroup.add(archMesh);

  // 5. Six purple meridian panel seams converging at the top button
  const seamAngles = [
    0,
    Math.PI / 3,
    (2 * Math.PI) / 3,
    Math.PI,
    (4 * Math.PI) / 3,
    (5 * Math.PI) / 3,
  ];
  for (const theta of seamAngles) {
    const isRearSeam = Math.abs(theta - Math.PI) < 0.01;
    const vStart = isRearSeam ? cutTopV : 0.02;
    const seamPts: THREE.Vector3[] = [];
    const steps = 20;
    for (let i = 0; i <= steps; i++) {
      const v = THREE.MathUtils.lerp(vStart, 0.985, i / steps);
      seamPts.push(domePoint(theta, v, 0.008));
    }
    const seamCurve = new THREE.CatmullRomCurve3(seamPts);
    const seamGeo = new THREE.TubeGeometry(seamCurve, 24, 0.0155, 12, false);
    const seamMesh = new THREE.Mesh(seamGeo, materials.purpleTrimMat);
    capGroup.add(seamMesh);
  }

  // 6. Cute lime crown button (squatchee) at apex
  const buttonGeo = new THREE.SphereGeometry(0.046, 20, 16);
  buttonGeo.scale(1, 0.65, 1);
  const buttonMesh = new THREE.Mesh(buttonGeo, materials.limeBrightMat);
  buttonMesh.position.set(0, H + 0.014, 0);
  capGroup.add(buttonMesh);

  // 7. Bright chartreuse-lime upturned J-scoop visor + continuous purple outer perimeter piping
  const brimHalfSpan = 0.86;
  const brimU = 44;
  const brimV = 16;

  const evalBrimCenter = (s: number, w: number): THREE.Vector3 => {
    const theta = s * brimHalfSpan - 0.08;
    const rootPt = domePoint(theta, 0.025, 0.004);
    const crescent = Math.cos(s * Math.PI * 0.5);
    const wingBias = 1.0 - 0.1 * s;
    const reach = 0.265 * Math.pow(crescent, 0.82) * wingBias * w;

    const dirX = Math.sin(theta * 0.78);
    const dirZ = Math.cos(theta * 0.78);
    const liftY =
      reach * 0.4 +
      0.095 * w * w * crescent +
      0.024 * Math.sin(w * Math.PI) * crescent -
      0.016 * s * s * w;

    return new THREE.Vector3(
      rootPt.x + dirX * reach,
      rootPt.y + liftY,
      rootPt.z + dirZ * reach
    );
  };

  const brimThickness = 0.032;
  const brimPos: number[] = [];
  const brimNormals: number[] = [];
  const brimIdx: number[] = [];

  for (let side = 0; side < 2; side++) {
    const ySign = side === 0 ? 1 : -1;
    for (let iv = 0; iv <= brimV; iv++) {
      const w = iv / brimV;
      for (let iu = 0; iu <= brimU; iu++) {
        const s = (iu / brimU) * 2 - 1;
        const p = evalBrimCenter(s, w);
        const edgeTaper = Math.sin(w * Math.PI * 0.85 + 0.15);
        p.y += ySign * (brimThickness * 0.5) * edgeTaper;
        brimPos.push(p.x, p.y, p.z);

        // Upward-and-outward normal bias on both faces so the scooped inner dish of the visor
        // catches the studio key/hemisphere light brightly like soft chartreuse clay (never muddy shadow!)
        const nx = s * 0.22;
        const ny = side === 0 ? 0.88 : 0.58;
        const nz = side === 0 ? 0.35 : 0.78;
        const nLen = Math.hypot(nx, ny, nz) || 1;
        brimNormals.push(nx / nLen, ny / nLen, nz / nLen);
      }
    }
  }

  const bStride = brimU + 1;
  const layerVerts = (brimV + 1) * bStride;
  for (let side = 0; side < 2; side++) {
    const offset = side * layerVerts;
    for (let iv = 0; iv < brimV; iv++) {
      for (let iu = 0; iu < brimU; iu++) {
        const a = offset + iv * bStride + iu;
        const b = offset + (iv + 1) * bStride + iu;
        const c = offset + (iv + 1) * bStride + (iu + 1);
        const d = offset + iv * bStride + (iu + 1);
        if (side === 0) {
          brimIdx.push(a, b, d);
          brimIdx.push(b, c, d);
        } else {
          brimIdx.push(a, d, b);
          brimIdx.push(b, d, c);
        }
      }
    }
  }

  const brimGeo = new THREE.BufferGeometry();
  brimGeo.setAttribute("position", new THREE.Float32BufferAttribute(brimPos, 3));
  brimGeo.setAttribute(
    "normal",
    new THREE.Float32BufferAttribute(brimNormals, 3)
  );
  brimGeo.setIndex(brimIdx);

  const brimMat = materials.limeBrightMat.clone();
  brimMat.side = THREE.DoubleSide;
  const brimMesh = new THREE.Mesh(brimGeo, brimMat);
  brimMesh.castShadow = false;
  brimMesh.receiveShadow = false;
  capGroup.add(brimMesh);

  const brimEdgePts: THREE.Vector3[] = [];
  for (let iu = 0; iu <= brimU; iu++) {
    const s = (iu / brimU) * 2 - 1;
    brimEdgePts.push(evalBrimCenter(s, 1.0));
  }
  const brimEdgeCurve = new THREE.CatmullRomCurve3(brimEdgePts);
  const brimEdgeGeo = new THREE.TubeGeometry(
    brimEdgeCurve,
    56,
    0.022,
    14,
    false
  );
  const brimEdgeMesh = new THREE.Mesh(brimEdgeGeo, materials.purpleTrimMat);
  brimEdgeMesh.castShadow = true;
  capGroup.add(brimEdgeMesh);

  return capGroup;
}

/**
 * Builds the plump lime takeaway drink cup, overhanging lid, purple collar ring,
 * and chunky two-tone bent straw (lime tube + purple outer spine stripe & tip rim).
 */
function buildDrinkCupProp(materials: {
  limeMat: THREE.MeshPhysicalMaterial;
  limeBrightMat: THREE.MeshPhysicalMaterial;
  purpleTrimMat: THREE.MeshPhysicalMaterial;
}): THREE.Group {
  const cupGroup = new THREE.Group();

  const lathePts: THREE.Vector2[] = [
    new THREE.Vector2(0.0, -0.245),
    new THREE.Vector2(0.142, -0.245),
    new THREE.Vector2(0.168, -0.236),
    new THREE.Vector2(0.178, -0.21),
    new THREE.Vector2(0.222, 0.185),
    new THREE.Vector2(0.224, 0.215),
    new THREE.Vector2(0.0, 0.215),
  ];
  const cupBodyGeo = new THREE.LatheGeometry(lathePts, 48);
  cupBodyGeo.computeVertexNormals();
  const cupBodyMesh = new THREE.Mesh(cupBodyGeo, materials.limeMat);
  cupBodyMesh.castShadow = true;
  cupBodyMesh.receiveShadow = true;
  cupGroup.add(cupBodyMesh);

  const collarGeo = new THREE.TorusGeometry(0.228, 0.025, 18, 48);
  collarGeo.rotateX(Math.PI / 2);
  const collarMesh = new THREE.Mesh(collarGeo, materials.purpleTrimMat);
  collarMesh.position.y = 0.2;
  collarMesh.castShadow = true;
  cupGroup.add(collarMesh);

  const lidPts: THREE.Vector2[] = [
    new THREE.Vector2(0.0, 0.212),
    new THREE.Vector2(0.23, 0.212),
    new THREE.Vector2(0.244, 0.228),
    new THREE.Vector2(0.244, 0.262),
    new THREE.Vector2(0.228, 0.278),
    new THREE.Vector2(0.0, 0.28),
  ];
  const lidGeo = new THREE.LatheGeometry(lidPts, 48);
  lidGeo.computeVertexNormals();
  const lidMesh = new THREE.Mesh(lidGeo, materials.limeBrightMat);
  lidMesh.castShadow = true;
  lidMesh.receiveShadow = true;
  cupGroup.add(lidMesh);

  const strawPts = [
    new THREE.Vector3(0.0, 0.25, 0.0),
    new THREE.Vector3(0.0, 0.34, 0.0),
    new THREE.Vector3(0.008, 0.425, 0.0),
    new THREE.Vector3(0.042, 0.468, 0.0),
    new THREE.Vector3(0.145, 0.555, 0.0),
  ];
  const strawCurve = new THREE.CatmullRomCurve3(strawPts);
  const strawGeo = new THREE.TubeGeometry(strawCurve, 36, 0.029, 18, false);
  const strawMesh = new THREE.Mesh(strawGeo, materials.limeBrightMat);
  strawMesh.castShadow = true;
  cupGroup.add(strawMesh);

  const spinePts = [
    new THREE.Vector3(-0.019, 0.268, 0.004),
    new THREE.Vector3(-0.019, 0.352, 0.004),
    new THREE.Vector3(-0.011, 0.438, 0.004),
    new THREE.Vector3(0.025, 0.484, 0.004),
    new THREE.Vector3(0.132, 0.57, 0.004),
  ];
  const spineCurve = new THREE.CatmullRomCurve3(spinePts);
  const spineGeo = new THREE.TubeGeometry(spineCurve, 36, 0.0185, 14, false);
  const spineMesh = new THREE.Mesh(spineGeo, materials.purpleTrimMat);
  cupGroup.add(spineMesh);

  const tipRingGeo = new THREE.TorusGeometry(0.024, 0.009, 12, 24);
  tipRingGeo.rotateY(Math.PI / 2);
  tipRingGeo.rotateZ(-0.76);
  const tipRingMesh = new THREE.Mesh(tipRingGeo, materials.purpleTrimMat);
  tipRingMesh.position.set(0.146, 0.556, 0.0);
  cupGroup.add(tipRingMesh);

  return cupGroup;
}

/**
 * Builds a soft radial Gaussian floor shadow mesh with premultiplied-safe blending.
 */
function buildFloorShadowMesh(): THREE.Mesh {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const grad = ctx.createRadialGradient(128, 128, 6, 128, 128, 122);
    grad.addColorStop(0.0, "rgba(74, 42, 114, 0.72)");
    grad.addColorStop(0.38, "rgba(92, 58, 134, 0.46)");
    grad.addColorStop(0.72, "rgba(116, 82, 160, 0.16)");
    grad.addColorStop(1.0, "rgba(116, 82, 160, 0.0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 256, 256);
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  const geo = new THREE.PlaneGeometry(2.15, 1.28);
  const mat = new THREE.MeshBasicMaterial({
    map: tex,
    transparent: true,
    depthWrite: false,
    toneMapped: false,
    blending: THREE.CustomBlending,
    blendSrc: THREE.SrcAlphaFactor,
    blendDst: THREE.OneMinusSrcAlphaFactor,
    blendSrcAlpha: THREE.OneFactor,
    blendDstAlpha: THREE.OneMinusSrcAlphaFactor,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.rotation.x = -Math.PI / 2 + 0.16;
  mesh.position.set(0, -1.02, -0.05);
  return mesh;
}

/**
 * Helper to build a smooth 3D arc seated flush on the recessed inner face surface.
 */
function buildFaceArcMesh(
  cx: number,
  cy: number,
  width: number,
  archHeight: number,
  tubeRadius: number,
  mat: THREE.Material
): THREE.Group {
  const grp = new THREE.Group();
  const pts: THREE.Vector3[] = [];
  const steps = 18;
  for (let i = 0; i <= steps; i++) {
    const u = (i / steps) * 2 - 1;
    const x = cx + u * (width * 0.5);
    const y = cy + (1 - u * u) * archHeight;
    const z = getInnerFaceZ(x, y) + 0.008;
    pts.push(new THREE.Vector3(x, y, z));
  }
  const curve = new THREE.CatmullRomCurve3(pts);
  const tubeGeo = new THREE.TubeGeometry(curve, 24, tubeRadius, 12, false);
  const mesh = new THREE.Mesh(tubeGeo, mat);
  grp.add(mesh);

  const capGeo = new THREE.SphereGeometry(tubeRadius * 0.98, 12, 12);
  const capStart = new THREE.Mesh(capGeo, mat);
  capStart.position.copy(pts[0]);
  const capEnd = new THREE.Mesh(capGeo, mat);
  capEnd.position.copy(pts[pts.length - 1]);
  grp.add(capStart, capEnd);

  return grp;
}

/**
 * Builds the complete lime mochi character rig, materials, props, and expressions.
 */
export function createMascotRig(): MascotRigHandles {
  const root = new THREE.Group();
  const floatGroup = new THREE.Group();
  root.add(floatGroup);

  const bodyMat = new THREE.MeshPhysicalMaterial({
    vertexColors: true,
    roughness: 0.7,
    metalness: 0.0,
    sheen: 0.14,
    sheenRoughness: 0.82,
    sheenColor: new THREE.Color(0xe5f098),
    clearcoat: 0.0,
  });

  const limeMat = new THREE.MeshPhysicalMaterial({
    color: 0xb5ca4a,
    roughness: 0.7,
    metalness: 0.0,
    sheen: 0.14,
    sheenRoughness: 0.82,
    sheenColor: new THREE.Color(0xe5f098),
    clearcoat: 0.0,
  });

  const limeBrightMat = new THREE.MeshPhysicalMaterial({
    color: 0xbed252,
    roughness: 0.66,
    metalness: 0.0,
    sheen: 0.14,
    sheenRoughness: 0.82,
    sheenColor: new THREE.Color(0xebf5a2),
    clearcoat: 0.0,
  });

  const purpleTrimMat = new THREE.MeshPhysicalMaterial({
    color: 0x877295,
    roughness: 0.64,
    metalness: 0.0,
    sheen: 0.14,
    sheenRoughness: 0.82,
    sheenColor: new THREE.Color(0xd2c0e0),
    clearcoat: 0.0,
  });

  const plumFeatureMat = new THREE.MeshPhysicalMaterial({
    color: 0x6b5878,
    roughness: 0.56,
    metalness: 0.0,
    sheen: 0.12,
    sheenRoughness: 0.8,
    sheenColor: new THREE.Color(0xb6a2c6),
    clearcoat: 0.0,
  });

  const freckleMat = new THREE.MeshPhysicalMaterial({
    color: 0x8ea03e,
    roughness: 0.74,
    metalness: 0.0,
  });

  const capInnerMat = new THREE.MeshStandardMaterial({
    color: 0x485622,
    roughness: 0.9,
    metalness: 0.0,
    side: THREE.BackSide,
  });

  // 1. Sculpted Pear-Mochi Body with Recessed Face Hood
  const bodyGeo = buildSculptedBodyGeometry();
  const bodyMesh = new THREE.Mesh(bodyGeo, bodyMat);
  bodyMesh.castShadow = true;
  bodyMesh.receiveShadow = true;
  floatGroup.add(bodyMesh);

  // 2. Temple Freckles on both upper cheeks behind the face hood rim
  const freckleOffsets = [
    { dy: 0.27, dz: 0.44, r: 0.0115 },
    { dy: 0.23, dz: 0.5, r: 0.0125 },
    { dy: 0.19, dz: 0.43, r: 0.011 },
    { dy: 0.24, dz: 0.37, r: 0.011 },
    { dy: 0.15, dz: 0.48, r: 0.01 },
  ];
  const freckleGeo = new THREE.SphereGeometry(1, 10, 10);
  for (const side of [-1, 1]) {
    for (const f of freckleOffsets) {
      const dot = new THREE.Mesh(freckleGeo, freckleMat);
      dot.scale.set(f.r * 0.6, f.r, f.r);
      const fx = side * Math.sqrt(Math.max(0.1, 0.75 - f.dz * f.dz));
      dot.position.set(fx, f.dy, f.dz);
      floatGroup.add(dot);
    }
  }

  // 3. Belly 'x' Stitch at lower front belly center
  const bellyStitchGroup = new THREE.Group();
  const bellyY = -0.45;
  const bellyZ = 0.832;
  bellyStitchGroup.position.set(0, bellyY, bellyZ);
  bellyStitchGroup.rotation.x = 0.35;

  const stitchCapsuleGeo = new THREE.CapsuleGeometry(0.019, 0.075, 10, 16);
  const stitch1 = new THREE.Mesh(stitchCapsuleGeo, plumFeatureMat);
  stitch1.rotation.z = Math.PI * 0.26;
  stitch1.scale.set(1, 1, 0.72);
  const stitch2 = new THREE.Mesh(stitchCapsuleGeo, plumFeatureMat);
  stitch2.rotation.z = -Math.PI * 0.26;
  stitch2.scale.set(1, 1, 0.72);
  bellyStitchGroup.add(stitch1, stitch2);
  floatGroup.add(bellyStitchGroup);

  // 4. Sideways 6-Panel Baseball Cap seated snugly on the broad dome
  const capGroup = buildBaseballCap({
    limeMat,
    limeBrightMat,
    purpleTrimMat,
    capInnerMat,
  });
  capGroup.position.set(0.055, 0.725, 0.012);
  capGroup.rotation.order = "YXZ";
  capGroup.rotation.y = -0.52;
  capGroup.rotation.x = -0.09;
  capGroup.rotation.z = -0.17;
  floatGroup.add(capGroup);

  // 5. Left Arm (+X in Front View): closed manifold sculpted bean arm tucked snugly along the hip
  const leftArmGroup = new THREE.Group();
  leftArmGroup.position.set(0.9, -0.02, -0.04);
  const leftArmGeo = buildSculptedLeftArmGeometry();
  const leftArmMesh = new THREE.Mesh(leftArmGeo, limeMat);
  leftArmMesh.castShadow = true;
  leftArmMesh.receiveShadow = true;
  leftArmGroup.add(leftArmMesh);
  floatGroup.add(leftArmGroup);

  // 6. Right Arm + Drink Cup Group (-X in Front View)
  const rightArmHoldGroup = new THREE.Group();
  floatGroup.add(rightArmHoldGroup);

  const cupGroup = buildDrinkCupProp({
    limeMat,
    limeBrightMat,
    purpleTrimMat,
  });
  cupGroup.position.set(-0.76, -0.12, 0.8);
  cupGroup.rotation.set(0.05, 0.0, 0.07);
  rightArmHoldGroup.add(cupGroup);

  // Helper to attach a plump paw mitt at the end of each pose's arm curve
  const buildArmWithPaw = (pts: THREE.Vector3[]): THREE.Group => {
    const grp = new THREE.Group();
    const armGeo = buildTaperedCapsuleCurve(
      pts,
      (t) => 0.134 + 0.038 * Math.sin(t * Math.PI * 0.85),
      36,
      24,
      1.0,
      1.08
    );
    const armMesh = new THREE.Mesh(armGeo, limeMat);
    armMesh.castShadow = true;
    armMesh.receiveShadow = true;
    grp.add(armMesh);

    const pawGeo = new THREE.SphereGeometry(0.134, 24, 20);
    pawGeo.scale(1.08, 0.96, 0.94);
    const pawMesh = new THREE.Mesh(pawGeo, limeMat);
    pawMesh.position.copy(pts[pts.length - 1]);
    pawMesh.castShadow = true;
    pawMesh.receiveShadow = true;
    grp.add(pawMesh);
    return grp;
  };

  // 6a. Rest Right Arm (connects shoulder (-0.75, 0.01, 0.04) -> rest cup paw (-0.84, -0.16, 0.86))
  const restRightArmGrp = buildArmWithPaw([
    new THREE.Vector3(-0.75, 0.01, 0.04),
    new THREE.Vector3(-0.96, -0.09, 0.36),
    new THREE.Vector3(-0.95, -0.16, 0.66),
    new THREE.Vector3(-0.84, -0.16, 0.86),
  ]);
  rightArmHoldGroup.add(restRightArmGrp);

  // 6b. Listen Right Arm (connects shoulder (-0.75, 0.0, 0.06) -> raised attentive cup (-0.46, -0.32, 0.86))
  const listenRightArmGrp = buildArmWithPaw([
    new THREE.Vector3(-0.75, 0.0, 0.06),
    new THREE.Vector3(-0.84, -0.14, 0.38),
    new THREE.Vector3(-0.7, -0.26, 0.68),
    new THREE.Vector3(-0.46, -0.32, 0.86),
  ]);
  listenRightArmGrp.visible = false;
  rightArmHoldGroup.add(listenRightArmGrp);

  // 6c. Sip Right Arm (connects shoulder (-0.75, 0.0, 0.06) -> sipping cup (-0.42, -0.28, 0.88))
  const sipRightArmGrp = buildArmWithPaw([
    new THREE.Vector3(-0.75, 0.0, 0.06),
    new THREE.Vector3(-0.82, -0.14, 0.4),
    new THREE.Vector3(-0.66, -0.25, 0.7),
    new THREE.Vector3(-0.42, -0.28, 0.88),
  ]);
  sipRightArmGrp.visible = false;
  rightArmHoldGroup.add(sipRightArmGrp);

  // 6d. Hug Right Arm for Guardrail `> ◡ <` (sweeps smoothly across front belly to chest cup (-0.12, -0.42, 0.91))
  const hugRightArmGrp = buildArmWithPaw([
    new THREE.Vector3(-0.75, -0.02, 0.06),
    new THREE.Vector3(-0.78, -0.21, 0.42),
    new THREE.Vector3(-0.5, -0.37, 0.76),
    new THREE.Vector3(-0.12, -0.42, 0.91),
  ]);
  hugRightArmGrp.visible = false;
  rightArmHoldGroup.add(hugRightArmGrp);

  const showRightArmVariant = (
    mode: "rest" | "listen" | "sip" | "hug"
  ) => {
    restRightArmGrp.visible = mode === "rest";
    listenRightArmGrp.visible = mode === "listen";
    sipRightArmGrp.visible = mode === "sip";
    hugRightArmGrp.visible = mode === "hug";
  };

  // 7. Crisp 3D Expressions seated flush on the recessed inner face surface
  const faceGroup = new THREE.Group();
  floatGroup.add(faceGroup);

  const eyeX = 0.172;
  const eyeY = 0.225;
  const eyeZ = getInnerFaceZ(eyeX, eyeY) + 0.008;

  // 7a. Vertical Pill Eyes `| |` (ready & listening)
  const pillEyes = new THREE.Group();
  const pillEyeGeo = new THREE.CapsuleGeometry(0.023, 0.062, 12, 18);
  pillEyeGeo.scale(1, 1, 0.65);
  const leftPillEye = new THREE.Mesh(pillEyeGeo, plumFeatureMat);
  leftPillEye.position.set(-eyeX, eyeY, eyeZ);
  const rightPillEye = new THREE.Mesh(pillEyeGeo, plumFeatureMat);
  rightPillEye.position.set(eyeX, eyeY, eyeZ);
  pillEyes.add(leftPillEye, rightPillEye);
  faceGroup.add(pillEyes);

  // 7b. Peaceful Closed Downward Crescent Eyes `︶ ︶` (processing zen sip)
  const closedDownEyes = new THREE.Group();
  const leftClosedArc = buildFaceArcMesh(
    -eyeX,
    eyeY + 0.012,
    0.122,
    -0.028,
    0.0165,
    plumFeatureMat
  );
  const rightClosedArc = buildFaceArcMesh(
    eyeX,
    eyeY + 0.012,
    0.122,
    -0.028,
    0.0165,
    plumFeatureMat
  );
  closedDownEyes.add(leftClosedArc, rightClosedArc);
  closedDownEyes.visible = false;
  faceGroup.add(closedDownEyes);

  // 7c. Happy Upward Arch Eyes `^ ^` (executing cheer & happy sip)
  const happyArchEyes = new THREE.Group();
  const leftHappyArc = buildFaceArcMesh(
    -eyeX,
    eyeY - 0.006,
    0.124,
    0.036,
    0.017,
    plumFeatureMat
  );
  const rightHappyArc = buildFaceArcMesh(
    eyeX,
    eyeY - 0.006,
    0.124,
    0.036,
    0.017,
    plumFeatureMat
  );
  happyArchEyes.add(leftHappyArc, rightHappyArc);
  happyArchEyes.visible = false;
  faceGroup.add(happyArchEyes);

  // 7d. Squint Chevron Eyes `> <` (guardrail hug & error wince)
  const squintChevronEyes = new THREE.Group();
  const buildChevronEye = (side: -1 | 1): THREE.Group => {
    const g = new THREE.Group();
    const cx = side * eyeX;
    const apexX = cx - side * 0.042;
    const outerX = cx + side * 0.046;
    const topPt = new THREE.Vector3(
      outerX,
      eyeY + 0.038,
      getInnerFaceZ(outerX, eyeY + 0.038) + 0.008
    );
    const midPt = new THREE.Vector3(
      apexX,
      eyeY,
      getInnerFaceZ(apexX, eyeY) + 0.009
    );
    const botPt = new THREE.Vector3(
      outerX,
      eyeY - 0.038,
      getInnerFaceZ(outerX, eyeY - 0.038) + 0.008
    );

    const seg1 = new THREE.LineCurve3(topPt, midPt);
    const seg2 = new THREE.LineCurve3(midPt, botPt);
    const r = 0.0165;
    const m1 = new THREE.Mesh(
      new THREE.TubeGeometry(seg1, 10, r, 12, false),
      plumFeatureMat
    );
    const m2 = new THREE.Mesh(
      new THREE.TubeGeometry(seg2, 10, r, 12, false),
      plumFeatureMat
    );
    const capSphere = new THREE.SphereGeometry(r, 10, 10);
    const cTop = new THREE.Mesh(capSphere, plumFeatureMat);
    cTop.position.copy(topPt);
    const cMid = new THREE.Mesh(capSphere, plumFeatureMat);
    cMid.position.copy(midPt);
    const cBot = new THREE.Mesh(capSphere, plumFeatureMat);
    cBot.position.copy(botPt);
    g.add(m1, m2, cTop, cMid, cBot);
    return g;
  };
  squintChevronEyes.add(buildChevronEye(-1), buildChevronEye(1));
  squintChevronEyes.visible = false;
  faceGroup.add(squintChevronEyes);

  // 7e. Cute Smile Mouth `◡` (ready, executing, guardrail)
  const smileMouth = buildFaceArcMesh(
    0,
    0.206,
    0.078,
    -0.024,
    0.0155,
    plumFeatureMat
  );
  faceGroup.add(smileMouth);

  // 7f. Attentive Sip-Ready Pucker Mouth `ˠ` (listening — top-right of ref_expr_zoom.png)
  const puckerMouth = new THREE.Group();
  const puckerTop = buildFaceArcMesh(
    0,
    0.208,
    0.056,
    -0.019,
    0.0145,
    plumFeatureMat
  );
  const puckerStemGeo = new THREE.CapsuleGeometry(0.0135, 0.024, 8, 12);
  const puckerStem = new THREE.Mesh(puckerStemGeo, plumFeatureMat);
  puckerStem.position.set(0, 0.178, getInnerFaceZ(0, 0.178) + 0.008);
  puckerMouth.add(puckerTop, puckerStem);
  puckerMouth.visible = false;
  faceGroup.add(puckerMouth);

  // 7g. Tiny Sipping Lip Cuff `c` / `o` (processing zen sip & happy sip)
  const sipMouth = new THREE.Group();
  const sipPts = [
    new THREE.Vector3(-0.006, 0.224, getInnerFaceZ(0, 0.224) + 0.01),
    new THREE.Vector3(0.016, 0.202, getInnerFaceZ(0, 0.202) + 0.011),
    new THREE.Vector3(-0.006, 0.18, getInnerFaceZ(0, 0.18) + 0.01),
  ];
  const sipCurve = new THREE.CatmullRomCurve3(sipPts);
  const sipMesh = new THREE.Mesh(
    new THREE.TubeGeometry(sipCurve, 16, 0.015, 12, false),
    plumFeatureMat
  );
  sipMouth.add(sipMesh);
  sipMouth.visible = false;
  faceGroup.add(sipMouth);

  // 7h. Worried / Apologetic Wince Mouth `︵` (error)
  const worryMouth = buildFaceArcMesh(
    0,
    0.185,
    0.072,
    0.022,
    0.015,
    plumFeatureMat
  );
  worryMouth.visible = false;
  faceGroup.add(worryMouth);

  // 8. Smooth Curved Lavender Bounce Motion Lines (`˘ ˘`) below lower-right hip
  const bounceLinesGroup = new THREE.Group();
  const buildSmoothBounceTick = (
    cx: number,
    cy: number,
    length: number,
    angleRad: number,
    sag: number
  ) => {
    const grp = new THREE.Group();
    const pts: THREE.Vector3[] = [];
    const steps = 16;
    const cosA = Math.cos(angleRad);
    const sinA = Math.sin(angleRad);
    for (let i = 0; i <= steps; i++) {
      const u = (i / steps) * 2 - 1;
      const along = u * (length * 0.5);
      const perp = (u * u - 1) * sag;
      const px = cx + along * cosA - perp * sinA;
      const py = cy + along * sinA + perp * cosA;
      pts.push(new THREE.Vector3(px, py, 0.34));
    }
    const curve = new THREE.CatmullRomCurve3(pts);
    const r = 0.0175;
    const tube = new THREE.Mesh(
      new THREE.TubeGeometry(curve, 20, r, 12, false),
      plumFeatureMat
    );
    const capGeo = new THREE.SphereGeometry(r * 0.98, 10, 10);
    const c0 = new THREE.Mesh(capGeo, plumFeatureMat);
    c0.position.copy(pts[0]);
    const c1 = new THREE.Mesh(capGeo, plumFeatureMat);
    c1.position.copy(pts[pts.length - 1]);
    grp.add(tube, c0, c1);
    return grp;
  };
  bounceLinesGroup.add(
    buildSmoothBounceTick(0.52, -0.84, 0.135, 0.42, 0.015),
    buildSmoothBounceTick(0.69, -0.75, 0.12, 0.58, 0.015)
  );
  bounceLinesGroup.visible = false;
  floatGroup.add(bounceLinesGroup);

  // 9. Soft Elliptical Floor Shadow
  const floorShadowMesh = buildFloorShadowMesh();
  root.add(floorShadowMesh);

  const showExpression = (
    eyes: "pill" | "closedDown" | "happyArch" | "squintChevron",
    mouth: "smile" | "pucker" | "sip" | "worry"
  ) => {
    pillEyes.visible = eyes === "pill";
    closedDownEyes.visible = eyes === "closedDown";
    happyArchEyes.visible = eyes === "happyArch";
    squintChevronEyes.visible = eyes === "squintChevron";

    smileMouth.visible = mouth === "smile";
    puckerMouth.visible = mouth === "pucker";
    sipMouth.visible = mouth === "sip";
    worryMouth.visible = mouth === "worry";
  };

  /**
   * Deterministic pose & camera-turnaround snapshot setter for both audit inspection and animation targets.
   */
  const setPoseSnapshot = (
    variant: MascotPoseVariant,
    options?: {
      yaw?: number;
      pitch?: number;
      time?: number;
      showShadow?: boolean;
    }
  ) => {
    const yaw = options?.yaw ?? 0;
    const pitch = options?.pitch ?? 0;
    floorShadowMesh.visible = options?.showShadow ?? true;

    floatGroup.position.set(0, 0, 0);
    floatGroup.rotation.set(pitch, yaw, 0);
    floatGroup.scale.set(1, 1, 1);

    leftArmGroup.position.set(0.9, -0.02, -0.04);
    leftArmGroup.rotation.set(0, 0, 0);

    rightArmHoldGroup.position.set(0, 0, 0);
    rightArmHoldGroup.rotation.set(0, 0, 0);
    cupGroup.position.set(-0.76, -0.12, 0.8);
    cupGroup.rotation.set(0.05, 0.0, 0.07);
    showRightArmVariant("rest");

    pillEyes.scale.set(1, 1, 1);
    bounceLinesGroup.visible = false;

    if (variant === "ready") {
      showExpression("pill", "smile");
    } else if (variant === "listening") {
      showExpression("pill", "pucker");
      showRightArmVariant("listen");
      cupGroup.position.set(-0.37, -0.3, 0.8);
      cupGroup.rotation.set(0.0, 0.0, -0.26);
    } else if (variant === "processing") {
      showExpression("closedDown", "sip");
      showRightArmVariant("sip");
      cupGroup.position.set(-0.35, -0.26, 0.815);
      cupGroup.rotation.set(0.0, 0.0, -0.38);
    } else if (variant === "happy_sip") {
      showExpression("happyArch", "sip");
      showRightArmVariant("sip");
      cupGroup.position.set(-0.35, -0.26, 0.815);
      cupGroup.rotation.set(0.0, 0.0, -0.38);
    } else if (variant === "executing") {
      showExpression("happyArch", "smile");
      floatGroup.position.y = 0.055;
      bounceLinesGroup.visible = true;
    } else if (variant === "guardrail") {
      showExpression("squintChevron", "smile");
      showRightArmVariant("hug");
      if (options?.yaw === undefined) {
        floatGroup.rotation.y = 0.36;
      }
      cupGroup.position.set(-0.04, -0.4, 0.85);
      cupGroup.rotation.set(-0.06, -0.55, 0.04);
      leftArmGroup.position.set(0.84, -0.02, 0.1);
      leftArmGroup.rotation.set(-0.16, 0.0, 0.08);
    } else if (variant === "error") {
      showExpression("squintChevron", "worry");
      floatGroup.rotation.z = -0.1;
      floatGroup.rotation.x = 0.08;
    }
  };

  let nextBlinkTime = 2.2;
  const cupPosTarget = new THREE.Vector3(-0.76, -0.12, 0.8);
  const cupRotTarget = new THREE.Euler(0.05, 0.0, 0.07);
  const leftArmRotTarget = new THREE.Euler(0, 0, 0);

  const updateAnimation = (params: {
    state: MascotState;
    audioLevel: number;
    time: number;
    dt: number;
    pointerX: number;
    pointerY: number;
    clickImpulse: number;
    playfulOverride?: MascotPoseVariant | null;
  }) => {
    const {
      state,
      audioLevel,
      time: t,
      dt,
      pointerX,
      pointerY,
      clickImpulse,
      playfulOverride,
    } = params;

    const level = THREE.MathUtils.clamp(audioLevel, 0, 1);

    let activeVariant: MascotPoseVariant = playfulOverride || state;
    if (!playfulOverride && state === "ready") {
      const cycle = t % 9.5;
      if (cycle > 7.6 && cycle < 9.2) {
        activeVariant = "happy_sip";
      }
    } else if (!playfulOverride && state === "executing") {
      const execCycle = t % 5.2;
      if (execCycle > 3.6) {
        activeVariant = "happy_sip";
      }
    }

    let targetYawOffset = 0;
    let targetRollOffset = 0;
    let targetPitchOffset = 0;
    let bobFreq = 2.0;
    let bobAmp = 0.05;

    cupPosTarget.set(-0.76, -0.12, 0.8);
    cupRotTarget.set(0.05, 0.0, 0.07);
    leftArmRotTarget.set(0, 0, 0);
    bounceLinesGroup.visible = false;
    showRightArmVariant("rest");

    if (activeVariant === "ready") {
      showExpression("pill", "smile");
    } else if (activeVariant === "listening") {
      showExpression("pill", "pucker");
      showRightArmVariant("listen");
      cupPosTarget.set(-0.37, -0.3 + level * 0.025, 0.8);
      cupRotTarget.set(0.0, 0.0, -0.26);
      targetPitchOffset = 0.05;
      bobFreq = 2.8;
      bobAmp = 0.045 + level * 0.04;
    } else if (activeVariant === "processing") {
      showExpression("closedDown", "sip");
      showRightArmVariant("sip");
      cupPosTarget.set(-0.35, -0.26, 0.815);
      cupRotTarget.set(0.0, 0.0, -0.38);
      bobFreq = 2.3;
      bobAmp = 0.045;
    } else if (activeVariant === "happy_sip") {
      showExpression("happyArch", "sip");
      showRightArmVariant("sip");
      cupPosTarget.set(-0.35, -0.26, 0.815);
      cupRotTarget.set(0.0, 0.0, -0.38);
      bobFreq = 2.6;
      bobAmp = 0.05;
    } else if (activeVariant === "executing") {
      showExpression("happyArch", "smile");
      bobFreq = 4.2;
      bobAmp = 0.08;
      bounceLinesGroup.visible = Math.sin(t * bobFreq) > 0.15;
    } else if (activeVariant === "guardrail") {
      showExpression("squintChevron", "smile");
      showRightArmVariant("hug");
      targetYawOffset = 0.36;
      cupPosTarget.set(-0.04, -0.4, 0.85);
      cupRotTarget.set(-0.06, -0.55, 0.04);
      leftArmRotTarget.set(-0.16, 0, 0.08);
    } else if (activeVariant === "error") {
      showExpression("squintChevron", "worry");
      targetRollOffset = -0.1 + Math.sin(t * 2.4) * 0.04;
      targetPitchOffset = 0.08;
    }

    let clickHop = 0;
    let clickSpin = 0;
    if (clickImpulse > 0.001) {
      const p = 1 - clickImpulse;
      clickHop = Math.sin(p * Math.PI) * 0.12;
      clickSpin = Math.sin(p * Math.PI) * 0.42;
      bounceLinesGroup.visible = true;
    }

    const bobY = Math.sin(t * bobFreq) * bobAmp + clickHop;
    floatGroup.position.y = bobY;

    const shadowScale = THREE.MathUtils.clamp(1.0 - bobY * 0.85, 0.78, 1.12);
    floorShadowMesh.scale.set(shadowScale, shadowScale, 1);

    const squish =
      state === "listening"
        ? level * 0.035 * Math.sin(t * 14)
        : Math.sin(t * bobFreq * 2) * 0.01;
    floatGroup.scale.set(1 + squish, 1 - squish * 0.85, 1 + squish * 0.5);

    const targetRotY = pointerX * 0.26 + targetYawOffset + clickSpin;
    const targetRotX = -pointerY * 0.15 + targetPitchOffset;
    const targetRotZ = targetRollOffset;

    const lerpRate = Math.min(1, dt * 8.0);
    floatGroup.rotation.y = THREE.MathUtils.lerp(
      floatGroup.rotation.y,
      targetRotY,
      lerpRate
    );
    floatGroup.rotation.x = THREE.MathUtils.lerp(
      floatGroup.rotation.x,
      targetRotX,
      lerpRate
    );
    floatGroup.rotation.z = THREE.MathUtils.lerp(
      floatGroup.rotation.z,
      targetRotZ,
      lerpRate
    );

    cupGroup.position.lerp(cupPosTarget, lerpRate);
    cupGroup.rotation.x = THREE.MathUtils.lerp(
      cupGroup.rotation.x,
      cupRotTarget.x,
      lerpRate
    );
    cupGroup.rotation.y = THREE.MathUtils.lerp(
      cupGroup.rotation.y,
      cupRotTarget.y,
      lerpRate
    );
    cupGroup.rotation.z = THREE.MathUtils.lerp(
      cupGroup.rotation.z,
      cupRotTarget.z,
      lerpRate
    );

    leftArmGroup.rotation.x = THREE.MathUtils.lerp(
      leftArmGroup.rotation.x,
      leftArmRotTarget.x + Math.sin(t * bobFreq + 1.1) * 0.04,
      lerpRate
    );
    leftArmGroup.rotation.z = THREE.MathUtils.lerp(
      leftArmGroup.rotation.z,
      leftArmRotTarget.z,
      lerpRate
    );

    let eyeScaleY = 1.0;
    if (t > nextBlinkTime) {
      const blinkProg = (t - nextBlinkTime) / 0.15;
      if (blinkProg < 1) {
        eyeScaleY = Math.max(0.1, Math.abs(Math.cos(blinkProg * Math.PI)));
      } else {
        nextBlinkTime = t + 2.8 + Math.random() * 2.6;
      }
    }
    pillEyes.children.forEach((eye) => {
      eye.scale.set(1, eyeScaleY, 1);
    });
  };

  const dispose = () => {
    root.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.geometry.dispose();
        if (Array.isArray(obj.material)) {
          obj.material.forEach((m) => m.dispose());
        } else {
          obj.material.dispose();
        }
      }
    });
  };

  return {
    root,
    floatGroup,
    bodyMesh,
    capGroup,
    leftArmGroup,
    rightArmHoldGroup,
    cupGroup,
    faceGroup,
    bounceLinesGroup,
    floorShadowMesh,
    expressions: {
      pillEyes,
      closedDownEyes,
      happyArchEyes,
      squintChevronEyes,
      smileMouth,
      puckerMouth,
      sipMouth,
      worryMouth,
    },
    materials: {
      bodyMat,
      limeMat,
      limeBrightMat,
      purpleTrimMat,
      plumFeatureMat,
      freckleMat,
      capInnerMat,
    },
    setPoseSnapshot,
    updateAnimation,
    dispose,
  };
}

/**
 * Configures the soft clay studio lighting & environment on a scene + renderer.
 */
export function setupMascotStudioLighting(
  scene: THREE.Scene,
  renderer: THREE.WebGLRenderer,
  RoomEnvironmentClass: new () => THREE.Scene
): {
  pmremGenerator: THREE.PMREMGenerator;
  envTarget: THREE.WebGLRenderTarget;
  rimLight: THREE.DirectionalLight;
} {
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.98;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const pmremGenerator = new THREE.PMREMGenerator(renderer);
  const envTarget = pmremGenerator.fromScene(new RoomEnvironmentClass(), 0.04);
  scene.environment = envTarget.texture;
  scene.environmentIntensity = 0.22;

  const hemiLight = new THREE.HemisphereLight(0xfff9ff, 0xbfa2e2, 1.08);
  hemiLight.position.set(0, 5, 0);
  scene.add(hemiLight);

  const keyLight = new THREE.DirectionalLight(0xfffdf6, 1.05);
  keyLight.position.set(2.2, 5.2, 4.4);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.set(1024, 1024);
  keyLight.shadow.camera.near = 1;
  keyLight.shadow.camera.far = 14;
  const d = 2.6;
  keyLight.shadow.camera.left = -d;
  keyLight.shadow.camera.right = d;
  keyLight.shadow.camera.top = d;
  keyLight.shadow.camera.bottom = -d;
  keyLight.shadow.bias = -0.0005;
  keyLight.shadow.radius = 5;
  scene.add(keyLight);

  const fillLight = new THREE.DirectionalLight(0xf3e8ff, 0.38);
  fillLight.position.set(-3.5, 1.6, 3.2);
  scene.add(fillLight);

  const rimLight = new THREE.DirectionalLight(0xe4d0ff, 0.42);
  rimLight.position.set(-0.5, 3.0, -3.8);
  scene.add(rimLight);

  return { pmremGenerator, envTarget, rimLight };
}
