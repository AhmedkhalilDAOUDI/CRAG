// Ask-view hero: a particle "sea" behind the question box.
// Based on the GetLayers "Flow Wave" scene (free layer), recoloured to CRAG's palette, sized to the hero
// instead of the window, reduced to one render pass, and paused when off screen or for reduced motion.
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";

const hero = document.querySelector(".hero");
const canvas = document.getElementById("wave");

const C = {
  bg: "#0E1621", flameA: "#0E7C74", flameB: "#F6E05E", flameAmt: 0.14,
  atmo: "#9FE3DA", atmoCount: 300, atmoSize: 24, atmoSpeed: 1.0,
  low: "#0E1621", high: "#3FB8AC", opacity: 0.3, pointSize: 5.5, brightness: 0.5,
  waveHeight: 3, flow: 1, scale: 0.275, scrollRise: 1.0,
  camStartY: 7, camStartZ: 16, camEndY: 0.8, camEndZ: -2, lookStartZ: 2, lookEndZ: -16,
  parallax: 1.2, pointerRadius: 7.0, pointerStrength: 0.9,
};
const lerp = (a, b, t) => a + (b - a) * t;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const vec3 = (hex) => { const n = parseInt(hex.slice(1), 16); return new THREE.Vector3(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255); };

const SNOISE = `
vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x, 289.0);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}
float snoise(vec3 v){
  const vec2 C = vec2(1.0/6.0, 1.0/3.0); const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy)); vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz); vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy); vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + 1.0 * C.xxx; vec3 x2 = x0 - i2 + 2.0 * C.xxx; vec3 x3 = x0 - 1.0 + 3.0 * C.xxx;
  i = mod(i, 289.0);
  vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0)) + i.y + vec4(0.0, i1.y, i2.y, 1.0)) + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 1.0/7.0; vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z *ns.z);
  vec4 x_ = floor(j * ns.z); vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ *ns.x + ns.yyyy; vec4 y = y_ *ns.x + ns.yyyy; vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy); vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0)*2.0 + 1.0; vec4 s1 = floor(b1)*2.0 + 1.0; vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy; vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
  vec3 p0 = vec3(a0.xy,h.x); vec3 p1 = vec3(a0.zw,h.y); vec3 p2 = vec3(a1.xy,h.z); vec3 p3 = vec3(a1.zw,h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.5 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0); m = m * m;
  return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}`;

const renderer = new THREE.WebGL1Renderer({ canvas, antialias: true });
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000000);
scene.fog = new THREE.Fog(0x000000, 0, 15);
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 400);
camera.position.set(0, C.camStartY, C.camStartZ);
scene.add(camera);

// The rolling sheet: a sphere's vertices, reshaped into a noise field in the vertex shader.
const uniforms = {
  uTime: { value: 0 }, uStream: { value: 0 }, uAppear: { value: 0 },
  uColLow: { value: vec3(C.low) }, uColHigh: { value: vec3(C.high) }, uOpacity: { value: C.opacity },
  uSize: { value: C.pointSize }, uBrightness: { value: C.brightness }, uWaveHeight: { value: C.waveHeight },
  uFlow: { value: C.flow }, uScale: { value: C.scale }, uCursor: { value: new THREE.Vector3() },
  uRepelRadius: { value: C.pointerRadius }, uRepelStrength: { value: C.pointerStrength }, uActivity: { value: 0 },
};
const sheet = new THREE.Points(new THREE.SphereGeometry(4.2, 200, 600), new THREE.ShaderMaterial({
  uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  vertexShader: `
uniform float uTime; uniform float uStream; uniform float uSize; uniform float uWaveHeight; uniform float uFlow; uniform float uScale;
uniform vec3 uColLow; uniform vec3 uColHigh;
uniform vec3 uCursor; uniform float uRepelRadius; uniform float uRepelStrength; uniform float uActivity;
varying vec3 vColor;
${SNOISE}
void main() {
  vec3 wp = vec3(position.x * 13.0, 0.0, position.z * 25.0);
  wp.x += position.y * 6.0;
  float zc = wp.z + uStream;
  float wn = snoise(vec3(wp.x * 0.08, zc * 0.08, uTime * 0.15 * uFlow)) * 2.0;
  wn += snoise(vec3(wp.x * 0.16, zc * 0.16, uTime * 0.3 * uFlow)) * 0.8;
  wp.y += wn * uWaveHeight;
  vec4 modelPosition = modelMatrix * vec4(wp * uScale, 1.0);
  vec3 toP = modelPosition.xyz - uCursor;
  float fall = smoothstep(uRepelRadius, 0.0, length(toP));
  modelPosition.xyz += normalize(toP + vec3(0.0001)) * fall * uRepelStrength * uActivity;
  vec4 mvPosition = viewMatrix * modelPosition;
  vColor = mix(uColLow, uColHigh, clamp(smoothstep(-3.0, 3.0, position.y + position.x * 0.5), 0.0, 1.0));
  gl_PointSize = max(uSize * (10.0 / -mvPosition.z), 1.5);
  gl_Position = projectionMatrix * mvPosition;
}`,
  fragmentShader: `
uniform float uOpacity; uniform float uBrightness; uniform float uAppear;
varying vec3 vColor;
void main() {
  float ll = length(gl_PointCoord - 0.5);
  if (ll > 0.5) discard;
  gl_FragColor = vec4(vColor * uBrightness, smoothstep(0.5, 0.1, ll) * uOpacity * uAppear);
}`,
}));
sheet.frustumCulled = false;
scene.add(sheet);

// Drifting motes that travel with the camera.
const N = C.atmoCount, pos = new Float32Array(N * 3), sizes = new Float32Array(N), seeds = new Float32Array(N);
for (let i = 0; i < N; i++) {
  pos[i * 3] = 2 * Math.random() - 1; pos[i * 3 + 1] = 2 * Math.random() - 1; pos[i * 3 + 2] = 2 * Math.random() - 1;
  sizes[i] = C.atmoSize * (0.4 + Math.random()); seeds[i] = Math.random();
}
const moteGeo = new THREE.BufferGeometry();
moteGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
moteGeo.setAttribute("size", new THREE.BufferAttribute(sizes, 1));
moteGeo.setAttribute("seed", new THREE.BufferAttribute(seeds, 1));
const moteMat = new THREE.ShaderMaterial({
  uniforms: { uTime: { value: 0 }, uColor: { value: vec3(C.atmo) }, uRes: { value: new THREE.Vector2(1, 1) } },
  transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false,
  vertexShader: `
attribute float size; attribute float seed; uniform float uTime; uniform vec2 uRes;
varying float vA;
vec3 warp(vec3 p, float t){ float c=0.9,a=1.9,b=0.02,s=0.05; p*=2.;
  p.x+=c*sin(s*t+a*p.y)+t*b; p.y+=c*cos(s*t+a*p.x); p.y+=c*sin(s*t+a*p.z)+t*b;
  p.z+=c*cos(s*t+a*p.y); p.z+=c*sin(s*t+a*p.x)+t*b; p.x+=c*cos(s*t+a*p.z);
  return cos(p+vec3(1,2,4)); }
void main(){
  vec3 v = position*4.0 + warp(position, uTime)*1.2;
  vec4 mv = modelViewMatrix * vec4(v, 1.0);
  vA = (1.0 - smoothstep(5.0, 6.5, length(v))) * smoothstep(0.0, 0.5, -mv.z);
  gl_PointSize = max(size * uRes.y / 900.0 / -mv.z, 1.0);
  gl_Position = projectionMatrix * mv;
}`,
  fragmentShader: `
uniform vec3 uColor; varying float vA;
void main(){ float l = length(gl_PointCoord - 0.5); if (l > 0.5) discard;
  float tex = smoothstep(0.5, 0.0, l); gl_FragColor = vec4(uColor * tex, tex * vA * 0.6); }`,
});
const motes = new THREE.Points(moteGeo, moteMat);
motes.frustumCulled = false;
scene.add(motes);

// One pass: the scene over a vignetted navy background with slow corner flames.
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const finalPass = new ShaderPass({
  uniforms: { iTime: { value: 0 }, tDiffuse: { value: null }, uBg: { value: vec3(C.bg) },
              uFlameA: { value: vec3(C.flameA) }, uFlameB: { value: vec3(C.flameB) }, uFlameAmt: { value: C.flameAmt } },
  vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position, 1.0); }",
  fragmentShader: `
uniform float iTime; uniform sampler2D tDiffuse; uniform vec3 uBg; uniform vec3 uFlameA; uniform vec3 uFlameB; uniform float uFlameAmt;
varying vec2 vUv;
vec3 warp3d(vec3 pos, float t){ float curv=.8,a=1.9,b=0.7; pos*=2.;
  pos.x+=curv*sin(t+a*pos.y)+t*b; pos.y+=curv*cos(t+a*pos.x);
  pos.y+=curv*sin(t+a*pos.z)+t*b; pos.z+=curv*cos(t+a*pos.y);
  pos.z+=curv*sin(t+a*pos.x)+t*b; pos.x+=curv*cos(t+a*pos.z);
  return 0.5+0.5*cos(pos.xyz+vec3(1,2,4)); }
void main(){
  vec2 uv = 2.*vUv - 1.;
  vec3 w = pow(warp3d(vec3(uv.x, sin(uv.y), uv.y), iTime*1.5), vec3(1.5));
  vec3 flame = 1.5*uFlameA*w.x; flame*=w.y; flame += uFlameB*w.z;
  flame *= smoothstep(0.25, 1., abs(uv.y));
  float md = smoothstep(-0.7, 1., -uv.y*uv.x); flame *= md*md;
  gl_FragColor = vec4(uBg * (1.0 - 0.4 * length(uv)) + flame*uFlameAmt + texture2D(tDiffuse, vUv).xyz, 1.);
}`,
});
composer.addPass(finalPass);

// ---- input: scroll through the hero drives the camera dive; the pointer parts the surface
const still = matchMedia("(prefers-reduced-motion: reduce)");
let scrollTarget = 0, scrollSmooth = 0, scrollNow = 0;
const mouseTarget = { x: 0, y: 0 }, mouse = { x: 0, y: 0 };
const pointer = { world: new THREE.Vector3(), activity: 0, active: false, lastMove: 0 };
const readScroll = () => { const r = hero.getBoundingClientRect(); scrollTarget = clamp(-r.top / Math.max(r.height, 1), 0, 1); };
addEventListener("scroll", readScroll, { passive: true });
hero.addEventListener("pointermove", (e) => {
  const r = hero.getBoundingClientRect();
  mouseTarget.x = ((e.clientX - r.left) / r.width) * 2 - 1;
  mouseTarget.y = -(((e.clientY - r.top) / r.height) * 2 - 1);
  pointer.active = true; pointer.lastMove = performance.now();
}, { passive: true });
hero.addEventListener("pointerleave", () => { pointer.active = false; });

const ndc = new THREE.Vector3(), dir = new THREE.Vector3(), tgt = new THREE.Vector3();
function updatePointer() {
  tgt.set(0, 0, 0);
  if (pointer.active) {  // project the cursor onto the z = 0 plane
    ndc.set(mouse.x, mouse.y, 0.5).unproject(camera);
    dir.copy(ndc).sub(camera.position).normalize();
    if (Math.abs(dir.z) > 1e-4) { const t = -camera.position.z / dir.z; if (t > 0 && Number.isFinite(t)) tgt.copy(camera.position).addScaledVector(dir, t); }
  }
  pointer.world.lerp(tgt, 0.12);
  const idle = (performance.now() - pointer.lastMove) / 1000;
  pointer.activity += ((pointer.active && idle < 3 ? 1 : 0) - pointer.activity) * 0.06;
}

let stream = 0, last = performance.now() / 1000;
const born = performance.now();
function frame(appear) {
  const t = performance.now() / 1000, dt = Math.min(0.05, t - last); last = t;
  scrollSmooth = lerp(scrollSmooth, scrollTarget, 0.10); scrollNow = lerp(scrollNow, scrollSmooth, 0.06);
  mouse.x = lerp(mouse.x, mouseTarget.x, 0.06); mouse.y = lerp(mouse.y, mouseTarget.y, 0.06);
  stream += dt * C.flow * 8.0;
  uniforms.uTime.value = t; uniforms.uStream.value = stream;
  uniforms.uWaveHeight.value = C.waveHeight * (1 + scrollNow * C.scrollRise);
  const ea = Math.min(scrollNow / 0.35, 1), e = ea * ea * (3 - 2 * ea);
  camera.position.set(mouse.x * C.parallax, lerp(C.camStartY, C.camEndY, e) + mouse.y * C.parallax * 0.3, lerp(C.camStartZ, C.camEndZ, e));
  camera.lookAt(mouse.x * C.parallax * 0.5, lerp(0, 0.6, e), lerp(C.lookStartZ, C.lookEndZ, e));
  updatePointer();
  uniforms.uCursor.value.copy(pointer.world); uniforms.uActivity.value = pointer.activity;
  uniforms.uAppear.value = appear ?? clamp(((performance.now() - born) / 1000 - 0.2) / 1.4, 0, 1);
  moteMat.uniforms.uTime.value = t * C.atmoSpeed * 8.0; motes.position.copy(camera.position);
  finalPass.uniforms.iTime.value = t;
  composer.render();
}

function resize() {
  const w = hero.clientWidth, h = hero.clientHeight, dpr = Math.min(devicePixelRatio, 1.75);
  renderer.setPixelRatio(dpr); renderer.setSize(w, h, false);
  composer.setPixelRatio(dpr); composer.setSize(w, h);
  camera.aspect = w / Math.max(h, 1); camera.updateProjectionMatrix();
  moteMat.uniforms.uRes.value.set(w * dpr, h * dpr);
  readScroll();
  if (still.matches) frame(1);  // reduced motion: one still frame, redrawn only on resize
}
new ResizeObserver(resize).observe(hero);

// Render only while the hero is on screen, the tab is visible and motion is allowed.
let visible = false, raf = 0;
const loop = () => { frame(); raf = requestAnimationFrame(loop); };
function update() {
  const run = visible && !document.hidden && !still.matches;
  if (run && !raf) { last = performance.now() / 1000; raf = requestAnimationFrame(loop); }
  if (!run && raf) { cancelAnimationFrame(raf); raf = 0; }
}
new IntersectionObserver(([e]) => { visible = e.isIntersecting; update(); }).observe(hero);
document.addEventListener("visibilitychange", update);
still.addEventListener("change", () => { update(); if (still.matches) frame(1); });
hero.classList.add("live");
