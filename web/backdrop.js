// Background object: a frosted-glass document that glides to a new pose, with a full turn, when the view changes.
// Built from the GetLayers "SVG to 3D" tool (CRAG's own document SVG, frosted glass, #cf7d5c), with the rim lights
// re-tinted amber, no orbit controls (it sits behind the UI), one pose per view, and no motion for reduced-motion users.
import * as THREE from "three";
import { SVGLoader } from "three/addons/loaders/SVGLoader.js";
import { RectAreaLightUniformsLib } from "three/addons/lights/RectAreaLightUniformsLib.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { FXAAShader } from "three/addons/shaders/FXAAShader.js";

const SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 150"><path fill="#000000" fill-rule="evenodd" d="M12 4H80L112 36V138Q112 146 104 146H12Q4 146 4 138V12Q4 4 12 4ZM22 50H94V57H22ZM22 66H94V73H22ZM22 82H94V89H22ZM22 98H78V105H22ZM22 114H88V121H22ZM22 22H58V34H22Z"/><path fill="#000000" d="M84 8L108 32H90Q84 32 84 26Z"/></svg>`;
const BG = "#1a1b17", LIGHT = "#e3c26a", SPIN = 0.18, DIST = 420, FOV = 36;
// Where the document sits in each view: fx/fy as a fraction of the visible half-width/half-height, s as a scale.
const POSES = {
  ask:       { fx: 0.92, fy: 0.04, s: 0.58, rx: 0.06,  rz: -0.14 },
  documents: { fx: 0.86, fy: 0.46, s: 0.28, rx: 0.42,  rz: 0.24 },
  graph:     { fx: 0.46, fy: 0.74, s: 0.3,  rx: -1.05, rz: 0.06 },
};
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
const viewName = () => (POSES[location.hash.slice(1)] ? location.hash.slice(1) : "ask");

const canvas = document.getElementById("backdrop");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: "high-performance" });
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.useLegacyLights = false;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.8;  // GetLayers uses 1.05; dimmer so it stays in the background

const scene = new THREE.Scene();
scene.background = new THREE.Color(BG);
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
const camera = new THREE.PerspectiveCamera(FOV, 1, 1, 5000);
camera.position.set(0, 0, DIST);

// ---- geometry: every SVG path merged into one bevelled extrusion, centred and scaled into a 200-unit box
function buildGeometry() {
  const shapes = new SVGLoader().parse(SVG).paths.flatMap((p) => SVGLoader.createShapes(p));
  const box = new THREE.Box2(), holeSizes = [];
  for (const s of shapes) {
    s.getPoints(16).forEach((p) => box.expandByPoint(p));
    for (const h of s.holes) { const b = new THREE.Box2().setFromPoints(h.getPoints(16)), d = b.getSize(new THREE.Vector2()); holeSizes.push(Math.min(d.x, d.y)); }
  }
  const size = box.getSize(new THREE.Vector2()), sf = 200 / Math.max(size.x, size.y);
  const bevelSize = Math.max(0.18 / sf, Math.min(4 / sf, Math.min(...holeSizes, Infinity) * 0.38));  // stays below the thinnest hole
  const g = new THREE.ExtrudeGeometry(shapes, { depth: 60 / sf, bevelEnabled: true, bevelSize, bevelThickness: bevelSize * (2.4 / 1.45),
    bevelOffset: -0.2 * bevelSize, bevelSegments: 32, curveSegments: 20, steps: 2 });
  g.center();
  g.scale(sf, -sf, sf);  // SVG y points down
  for (const a of [g.attributes.position, g.attributes.uv]) {  // the mirror flipped the winding: swap corners 1 and 2
    for (let i = 0; i < a.count; i += 3) for (let c = 0; c < a.itemSize; c++) {
      const t = a.array[(i + 1) * a.itemSize + c]; a.array[(i + 1) * a.itemSize + c] = a.array[(i + 2) * a.itemSize + c]; a.array[(i + 2) * a.itemSize + c] = t;
    }
  }
  g.computeVertexNormals();
  return g;
}

// ---- frosted-glass materials: caps (group 0) and walls (group 1)
const caps = new THREE.MeshPhysicalMaterial({ color: "#825443", metalness: 0.03, roughness: 0.42, clearcoat: 0.42, clearcoatRoughness: 0.3,
  transmission: 0.5, ior: 1.46, thickness: 12, envMapIntensity: 1.5 });
const walls = new THREE.MeshPhysicalMaterial({ color: "#ad7a6a", emissive: "#3d271f", emissiveIntensity: 0.11, metalness: 0.03, roughness: 0.48,
  clearcoat: 0.3, transmission: 0.32, thickness: 8, envMapIntensity: 1.3 });
const doc = new THREE.Group();
doc.add(new THREE.Mesh(buildGeometry(), [caps, walls]));
scene.add(doc);

// ---- lights (rim + fill), tinted from one colour with GetLayers' HSL formula; they do not move with the document
const base = new THREE.Color(LIGHT), hsl = base.getHSL({}), sat = clamp(hsl.s * 0.96, 0.18, 0.94);
const tone = (l, k) => new THREE.Color().setHSL(hsl.h, clamp(sat * k, 0, 1), l);
RectAreaLightUniformsLib.init();
scene.add(new THREE.AmbientLight("#ffe6b0", 0.056));
for (const [col, power, w, h, pos, at] of [
  [tone(0.24, 0.82), 3.5, 240, 300, [-90, -40, 170], [0, 0, 0]],
  [tone(0.56, 1), 16.8, 72, 520, [-165, 20, -60], [-18, 0, 0]],
  [tone(0.56, 1), 15.4, 72, 520, [165, 10, -58], [18, 0, 0]],
  [tone(0.52, 0.5), 7, 150, 300, [120, 90, 160], [0, 0, 0]],
]) { const l = new THREE.RectAreaLight(col, power, w, h); l.position.set(...pos); l.lookAt(...at); scene.add(l); }

// ---- post: bloom on the rim highlights, ACES + sRGB, then FXAA
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.3, 0.5, 0.9);
bloom.strength = 0.14; bloom.radius = 0.6; bloom.threshold = 0.82;
composer.addPass(bloom);
composer.addPass(new OutputPass());
const fxaa = new ShaderPass(FXAAShader);
composer.addPass(fxaa);

// ---- poses: the document eases to the view's pose and makes one extra turn on the way
const still = matchMedia("(prefers-reduced-motion: reduce)");
let halfH = 1, halfW = 1;
const target = (name) => { const p = POSES[name], fit = Math.min(1, halfW / halfH); return { x: p.fx * halfW, y: p.fy * halfH, s: p.s * fit, rx: p.rx, rz: p.rz }; };
let from = null, to = null, startedAt = 0, spinY = 0, turn = 0;
const DURATION = 1.4;
function goTo(name, instant) {
  const now = { x: doc.position.x, y: doc.position.y, s: doc.scale.x, rx: doc.rotation.x, rz: doc.rotation.z };
  to = target(name);
  from = instant || still.matches ? to : now;
  startedAt = performance.now() / 1000;
  if (!instant && !still.matches) turn += Math.PI * 2;
}
addEventListener("hashchange", () => goTo(viewName()));

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight, dpr = Math.min(devicePixelRatio, 2);
  renderer.setPixelRatio(dpr); renderer.setSize(w, h, false);
  composer.setPixelRatio(dpr); composer.setSize(w, h);
  fxaa.material.uniforms.resolution.value.set(1 / (w * dpr), 1 / (h * dpr));
  camera.aspect = w / Math.max(h, 1); camera.updateProjectionMatrix();
  halfH = DIST * Math.tan(THREE.MathUtils.degToRad(FOV / 2)); halfW = halfH * camera.aspect;
  goTo(viewName(), true);
  if (!raf) frame();
}

let last = performance.now() / 1000, raf = 0, turnDone = 0;
function frame() {
  const t = performance.now() / 1000, dt = Math.min(0.05, t - last); last = t;
  const k = still.matches ? 1 : ease(clamp((t - startedAt) / DURATION, 0, 1));
  if (!still.matches) spinY += dt * SPIN;
  turnDone = turnDone + (turn - turnDone) * (still.matches ? 1 : Math.min(1, dt * 3.2));  // the extra turn settles with the move
  const bob = still.matches ? 0 : Math.sin(t * 0.6) * 2.5;
  doc.position.set(from.x + (to.x - from.x) * k, from.y + (to.y - from.y) * k + bob, 0);
  doc.scale.setScalar(from.s + (to.s - from.s) * k);
  doc.rotation.set(from.rx + (to.rx - from.rx) * k, spinY + turnDone, from.rz + (to.rz - from.rz) * k);
  composer.render();
}

// Animate only while the tab is visible and motion is allowed; otherwise draw single frames.
const loop = () => { frame(); raf = requestAnimationFrame(loop); };
function update() {
  const run = !document.hidden && !still.matches;
  if (run && !raf) { last = performance.now() / 1000; raf = requestAnimationFrame(loop); }
  if (!run && raf) { cancelAnimationFrame(raf); raf = 0; }
}
addEventListener("hashchange", () => { if (!raf) frame(); });
document.addEventListener("visibilitychange", update);
still.addEventListener("change", () => { goTo(viewName(), true); update(); frame(); });
resize();  // sets the first pose before the loop starts
new ResizeObserver(resize).observe(canvas);
update();
canvas.classList.add("live");
