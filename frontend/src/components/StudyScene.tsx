import { useEffect, useRef } from "react";

export default function StudyScene() {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    let disposeScene: (() => void) | null = null;

    const initialize = async () => {
      const THREE = await import("three");
      const host = hostRef.current;
      if (cancelled || !host) return;

      const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" });
      const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
    camera.position.set(0, 0, 8.6);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor(0x000000, 0);
    host.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xe7e6d8, 1.2));
    const keyLight = new THREE.DirectionalLight(0xf4b77a, 3.2);
    keyLight.position.set(-3, 4, 5);
    scene.add(keyLight);
    const fillLight = new THREE.PointLight(0x61aca3, 18, 12);
    fillLight.position.set(3, -1, 3);
    scene.add(fillLight);

    const sculpture = new THREE.Group();
    scene.add(sculpture);

    const core = new THREE.Mesh(
      new THREE.IcosahedronGeometry(0.86, 1),
      new THREE.MeshPhysicalMaterial({ color: 0xe66a4b, roughness: 0.26, metalness: 0.22, clearcoat: 0.8, clearcoatRoughness: 0.2 }),
    );
    core.position.set(0, 0.05, 0.28);
    sculpture.add(core);

    const wire = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.12, 1),
      new THREE.MeshBasicMaterial({ color: 0xf3dcb5, wireframe: true, transparent: true, opacity: 0.38 }),
    );
    wire.position.copy(core.position);
    sculpture.add(wire);

    const ringMaterial = new THREE.MeshBasicMaterial({ color: 0x9ac9b8, transparent: true, opacity: 0.7 });
    const ring = new THREE.Mesh(new THREE.TorusGeometry(1.7, 0.009, 8, 160), ringMaterial);
    ring.rotation.set(0.94, 0.26, -0.42);
    sculpture.add(ring);

    const orbit = new THREE.Group();
    orbit.rotation.set(0.94, 0.26, -0.42);
    sculpture.add(orbit);
    const nodeMaterial = new THREE.MeshStandardMaterial({ color: 0xd6c8a8, roughness: 0.36, metalness: 0.2, emissive: 0x41362a });
    for (let index = 0; index < 3; index += 1) {
      const angle = (index / 3) * Math.PI * 2 + 0.3;
      const node = new THREE.Mesh(new THREE.SphereGeometry(0.085, 18, 14), nodeMaterial);
      node.position.set(Math.cos(angle) * 1.7, Math.sin(angle) * 1.7, 0);
      orbit.add(node);
    }

    const paperMaterial = new THREE.MeshStandardMaterial({ color: 0xc8c8b9, roughness: 0.83, metalness: 0.02, side: THREE.DoubleSide });
    const coverMaterial = new THREE.MeshStandardMaterial({ color: 0x315a56, roughness: 0.52, metalness: 0.12 });
    const inkMaterial = new THREE.MeshBasicMaterial({ color: 0x576b63 });
    const makeBook = (positionX: number, positionY: number, positionZ: number, rotationY: number, uniformScale: number) => {
      const book = new THREE.Group();
      book.position.set(positionX, positionY, positionZ);
      book.rotation.set(-0.18, rotationY, -0.18);
      book.scale.setScalar(uniformScale);

      const pages = new THREE.Mesh(new THREE.BoxGeometry(1.24, 0.075, 1.7), paperMaterial);
      book.add(pages);
      const cover = new THREE.Mesh(new THREE.BoxGeometry(1.34, 0.055, 1.78), coverMaterial);
      cover.position.y = -0.055;
      book.add(cover);
      for (let line = 0; line < 4; line += 1) {
        const rule = new THREE.Mesh(new THREE.BoxGeometry(0.64 - line * 0.07, 0.008, 0.018), inkMaterial);
        rule.position.set(-0.08, 0.043, -0.43 + line * 0.16);
        book.add(rule);
      }
      sculpture.add(book);
    };
    makeBook(-1.28, -0.8, -0.2, -0.5, 0.78);
    makeBook(1.34, 0.78, -0.5, 0.66, 0.66);

    const base = new THREE.Mesh(
      new THREE.CylinderGeometry(1.65, 1.9, 0.16, 64),
      new THREE.MeshStandardMaterial({ color: 0x273d38, roughness: 0.58, metalness: 0.22 }),
    );
    base.position.set(0, -1.35, -0.4);
    sculpture.add(base);

    const resizeObserver = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width === 0 || height === 0) return;
      camera.aspect = width / height;
      camera.position.z = width < 500 ? 10.1 : 8.6;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    });
    resizeObserver.observe(host);

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    let pointerX = 0;
    let pointerY = 0;
    const handlePointerMove = (event: PointerEvent) => {
      const bounds = host.getBoundingClientRect();
      pointerX = ((event.clientX - bounds.left) / bounds.width - 0.5) * 0.22;
      pointerY = ((event.clientY - bounds.top) / bounds.height - 0.5) * 0.14;
    };
    const animate = (time: number) => {
      if (reduceMotion) {
        renderer.render(scene, camera);
        return;
      }

      sculpture.rotation.y += 0.0017;
      sculpture.rotation.x += (pointerY - sculpture.rotation.x) * 0.018;
      sculpture.rotation.z += (pointerX - sculpture.rotation.z) * 0.018;
      orbit.rotation.z += 0.001;
      core.rotation.y = time * 0.00012;
      renderer.render(scene, camera);
      frame = window.requestAnimationFrame(animate);
    };
    host.addEventListener("pointermove", handlePointerMove);
    frame = window.requestAnimationFrame(animate);

      disposeScene = () => {
      window.cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      host.removeEventListener("pointermove", handlePointerMove);
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach((material) => material.dispose());
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
    };

    void initialize().catch(() => {
      if (!cancelled && hostRef.current) hostRef.current.dataset.sceneFailed = "true";
    });
    return () => {
      cancelled = true;
      disposeScene?.();
    };
  }, []);

  return <div className="study-scene" ref={hostRef} role="img" aria-label="A 3D study sculpture connecting notes, source material, and ideas" />;
}