// Real Three.js renderer with OrbitControls — drop-in replacement for the
// boardsmith_ui static SVG isometric viewer. Same prop shape (`{ data }`).
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Board3DData, LayoutComponent } from "../types";

interface Board3DViewerProps {
  data: Board3DData | null;
}

const Board3DViewer = ({ data }: Board3DViewerProps) => {
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !data) return;

    const width = mount.clientWidth || 800;
    const height = mount.clientHeight || 600;

    // ── Scene + Camera + Renderer ────────────────────────────────────────
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0f1c);
    scene.fog = new THREE.Fog(0x0a0f1c, 200, 600);

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 2000);
    const boardW = data.board.width || 120;
    const boardH = data.board.height || 85;
    const dist = Math.max(boardW, boardH) * 1.6;
    camera.position.set(dist * 0.6, dist * 0.7, dist * 0.6);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(width, height);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    mount.appendChild(renderer.domElement);

    // ── Lights — multi-light setup for that "fab studio" look ────────────
    const ambient = new THREE.AmbientLight(0xeef3ff, 0.55);
    scene.add(ambient);

    const key = new THREE.DirectionalLight(0xffffff, 1.1);
    key.position.set(60, 120, 80);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.left   = -boardW;
    key.shadow.camera.right  =  boardW;
    key.shadow.camera.top    =  boardH;
    key.shadow.camera.bottom = -boardH;
    scene.add(key);

    const rim = new THREE.DirectionalLight(0xc87533, 0.45);
    rim.position.set(-90, 60, -50);
    scene.add(rim);

    const fill = new THREE.DirectionalLight(0x22d3ee, 0.3);
    fill.position.set(40, 30, -120);
    scene.add(fill);

    // ── Board (FR4) ──────────────────────────────────────────────────────
    const boardThickness = data.board.thickness ?? 1.6;
    const boardGeom = new THREE.BoxGeometry(boardW, boardThickness, boardH);
    const boardMat = new THREE.MeshStandardMaterial({
      color: 0x0d3b22,
      roughness: 0.85,
      metalness: 0.05,
      emissive: 0x021507,
      emissiveIntensity: 0.4,
    });
    const board = new THREE.Mesh(boardGeom, boardMat);
    board.receiveShadow = true;
    scene.add(board);

    // Subtle copper pour over the board face — gives that PCB green-and-glow look
    const pourGeom = new THREE.PlaneGeometry(boardW * 0.94, boardH * 0.94);
    const pourMat = new THREE.MeshStandardMaterial({
      color: 0x1f6b3e,
      roughness: 0.6,
      metalness: 0.2,
      transparent: true,
      opacity: 0.5,
    });
    const pour = new THREE.Mesh(pourGeom, pourMat);
    pour.rotation.x = -Math.PI / 2;
    pour.position.y = boardThickness / 2 + 0.005;
    scene.add(pour);

    // ── Coordinate transform: backend gives top-left mm, three.js uses centered ──
    const tx = (x: number) => x - boardW / 2;
    const tz = (y: number) => y - boardH / 2;
    const surfaceY = boardThickness / 2 + 0.02;

    // ── Copper traces on F.Cu ────────────────────────────────────────────
    const traceMat = new THREE.MeshStandardMaterial({
      color: 0xc87533,
      roughness: 0.35,
      metalness: 0.85,
      emissive: 0x331a08,
      emissiveIntensity: 0.6,
    });
    data.traces.forEach((seg) => {
      for (let i = 0; i < seg.points.length - 1; i++) {
        const [x1, y1] = seg.points[i];
        const [x2, y2] = seg.points[i + 1];
        const a = new THREE.Vector3(tx(x1), surfaceY, tz(y1));
        const b = new THREE.Vector3(tx(x2), surfaceY, tz(y2));
        const len = a.distanceTo(b);
        if (len < 0.01) continue;
        const traceGeom = new THREE.BoxGeometry(len, 0.18, 0.55);
        const trace = new THREE.Mesh(traceGeom, traceMat);
        trace.position.copy(a).lerp(b, 0.5);
        trace.rotation.y = -Math.atan2(b.z - a.z, b.x - a.x);
        trace.castShadow = true;
        trace.receiveShadow = true;
        scene.add(trace);
      }
    });

    // ── Ratsnest as floating cyan lines ──────────────────────────────────
    const ratsnestMat = new THREE.LineDashedMaterial({
      color: 0x22d3ee,
      dashSize: 1.2,
      gapSize: 0.8,
      transparent: true,
      opacity: 0.55,
    });
    data.ratsnest.forEach((line) => {
      const pts = [
        new THREE.Vector3(tx(line.from_point[0]), surfaceY + 1.2, tz(line.from_point[1])),
        new THREE.Vector3(tx(line.to_point[0]),   surfaceY + 1.2, tz(line.to_point[1])),
      ];
      const geo = new THREE.BufferGeometry().setFromPoints(pts);
      const ln = new THREE.Line(geo, ratsnestMat);
      ln.computeLineDistances();
      scene.add(ln);
    });

    // ── Components ───────────────────────────────────────────────────────
    const padMat = new THREE.MeshStandardMaterial({
      color: 0xf5c46b,
      roughness: 0.25,
      metalness: 0.9,
      emissive: 0x4a3008,
      emissiveIntensity: 0.4,
    });

    const makeLabel = (text: string, color = "#f5ead3"): THREE.Sprite => {
      const canvas = document.createElement("canvas");
      const padX = 12;
      const padY = 6;
      const fontSize = 36;
      const ctx = canvas.getContext("2d")!;
      ctx.font = `600 ${fontSize}px "IBM Plex Sans", sans-serif`;
      const w = Math.ceil(ctx.measureText(text).width) + padX * 2;
      const h = fontSize + padY * 2;
      canvas.width = w;
      canvas.height = h;
      ctx.font = `600 ${fontSize}px "IBM Plex Sans", sans-serif`;
      ctx.fillStyle = "rgba(10,15,28,0.78)";
      ctx.fillRect(0, 0, w, h);
      ctx.strokeStyle = "#c87533";
      ctx.lineWidth = 2;
      ctx.strokeRect(1, 1, w - 2, h - 2);
      ctx.fillStyle = color;
      ctx.textBaseline = "middle";
      ctx.textAlign = "center";
      ctx.fillText(text, w / 2, h / 2);
      const tex = new THREE.CanvasTexture(canvas);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.minFilter = THREE.LinearFilter;
      const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
      const sprite = new THREE.Sprite(mat);
      const scale = 0.04;
      sprite.scale.set(w * scale, h * scale, 1);
      return sprite;
    };

    data.components.forEach((comp: LayoutComponent) => {
      const group = new THREE.Group();
      const cx = tx(comp.x);
      const cz = tz(comp.y);
      const w = Math.max(comp.width, 1);
      const d = Math.max(comp.height, 1);

      // body
      const bodyHeight = Math.max(1.0, Math.min(w, d) * 0.4);
      const bodyMat = new THREE.MeshStandardMaterial({
        color: new THREE.Color(comp.color || "#334155"),
        roughness: 0.55,
        metalness: 0.25,
      });
      const body = new THREE.Mesh(new THREE.BoxGeometry(w, bodyHeight, d), bodyMat);
      body.position.set(0, surfaceY + bodyHeight / 2, 0);
      body.castShadow = true;
      body.receiveShadow = true;
      group.add(body);

      // top-side highlight strip
      const stripGeom = new THREE.PlaneGeometry(w * 0.92, d * 0.18);
      const stripMat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.12,
      });
      const strip = new THREE.Mesh(stripGeom, stripMat);
      strip.rotation.x = -Math.PI / 2;
      strip.position.set(0, surfaceY + bodyHeight + 0.01, -d / 2 + d * 0.18);
      group.add(strip);

      // pin-1 marker
      const pinDot = new THREE.Mesh(
        new THREE.CylinderGeometry(0.4, 0.4, 0.05, 16),
        new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0x666666, emissiveIntensity: 0.3 })
      );
      pinDot.position.set(-w / 2 + 1.0, surfaceY + bodyHeight + 0.03, -d / 2 + 1.0);
      group.add(pinDot);

      // pads
      comp.pads.forEach((pad) => {
        const pmesh = new THREE.Mesh(
          new THREE.CylinderGeometry(0.7, 0.7, 0.18, 24),
          padMat
        );
        pmesh.position.set(tx(pad.x) - cx, surfaceY + 0.05, tz(pad.y) - cz);
        pmesh.castShadow = true;
        group.add(pmesh);
      });

      // labels
      const partLabel = makeLabel(comp.type, "#f5ead3");
      partLabel.position.set(0, surfaceY + bodyHeight + 2.6, 0);
      group.add(partLabel);

      const refLabel = makeLabel(comp.ref, "#9ba6c2");
      refLabel.position.set(0, surfaceY + bodyHeight + 1.2, 0);
      refLabel.scale.multiplyScalar(0.7);
      group.add(refLabel);

      group.position.set(cx, 0, cz);
      group.rotation.y = (comp.rotation ?? 0) * (Math.PI / 180);
      scene.add(group);
    });

    // ── OrbitControls ────────────────────────────────────────────────────
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 30;
    controls.maxDistance = 600;
    controls.target.set(0, 0, 0);

    // ── Resize handling ──────────────────────────────────────────────────
    const handleResize = () => {
      if (!mount) return;
      const w = mount.clientWidth || width;
      const h = mount.clientHeight || height;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    const ro = new ResizeObserver(handleResize);
    ro.observe(mount);

    // ── Render loop ──────────────────────────────────────────────────────
    let raf = 0;
    const tick = () => {
      controls.update();
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };
    tick();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      renderer.dispose();
      scene.traverse((obj) => {
        if ((obj as THREE.Mesh).geometry) (obj as THREE.Mesh).geometry.dispose();
        const mat = (obj as THREE.Mesh).material;
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
        else if (mat) mat.dispose();
      });
      if (renderer.domElement.parentNode === mount) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, [data]);

  if (!data) return <div className="bs-skeleton h-full w-full" />;
  return <div ref={mountRef} className="h-full w-full" />;
};

export default Board3DViewer;
