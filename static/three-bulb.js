import * as THREE from "./vendor/three.module.min.js";

const host = document.querySelector("#bulb");
const canvas = host?.querySelector(".bulb__canvas");

if (host instanceof HTMLElement && canvas instanceof HTMLCanvasElement) {
  try {
    const renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
      powerPreference: "low-power",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 30);
    camera.position.set(0, 0.02, 7.2);

    const environmentCanvas = document.createElement("canvas");
    environmentCanvas.width = 1024;
    environmentCanvas.height = 512;
    const context = environmentCanvas.getContext("2d");
    if (!context) {
      throw new Error("Could not create the Three.js environment texture.");
    }

    const room = context.createLinearGradient(0, 0, 0, 512);
    room.addColorStop(0, "#66717a");
    room.addColorStop(0.35, "#293139");
    room.addColorStop(0.7, "#151a1e");
    room.addColorStop(1, "#50504b");
    context.fillStyle = room;
    context.fillRect(0, 0, 1024, 512);

    for (const panel of [
      { x: 60, y: 90, w: 95, h: 245, alpha: 0.85 },
      { x: 665, y: 38, w: 175, h: 185, alpha: 1 },
      { x: 900, y: 118, w: 68, h: 260, alpha: 0.65 },
      { x: 352, y: 0, w: 140, h: 52, alpha: 0.42 },
    ]) {
      context.save();
      context.shadowColor = "#fff4d7";
      context.shadowBlur = 45;
      context.fillStyle = `rgba(255, 244, 220, ${panel.alpha})`;
      context.fillRect(panel.x, panel.y, panel.w, panel.h);
      context.restore();
      const reflection = context.createLinearGradient(
        panel.x,
        panel.y,
        panel.x + panel.w,
        panel.y,
      );
      reflection.addColorStop(0, "rgba(255,255,255,0)");
      reflection.addColorStop(0.5, `rgba(255,249,232,${panel.alpha * 0.8})`);
      reflection.addColorStop(1, "rgba(255,255,255,0)");
      context.fillStyle = reflection;
      context.fillRect(panel.x, panel.y, panel.w, panel.h);
    }

    const environment = new THREE.CanvasTexture(environmentCanvas);
    environment.mapping = THREE.EquirectangularReflectionMapping;
    environment.colorSpace = THREE.SRGBColorSpace;
    scene.environment = environment;
    scene.environmentIntensity = 1.25;

    scene.add(new THREE.HemisphereLight(0xdce8f1, 0x29221a, 1.25));

    const keyLight = new THREE.DirectionalLight(0xffe6bd, 2.2);
    keyLight.position.set(-3, 4, 5);
    scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight(0xb9d9ef, 1.6);
    rimLight.position.set(3, 2, -3);
    scene.add(rimLight);

    const filamentLight = new THREE.PointLight(0xffa72e, 0, 4);
    filamentLight.position.set(0, 0.66, 0.05);
    scene.add(filamentLight);

    const model = new THREE.Group();
    scene.add(model);

    const glassProfile = [
      [0.34, -0.12],
      [0.39, -0.04],
      [0.43, 0.08],
      [0.53, 0.24],
      [0.68, 0.46],
      [0.84, 0.74],
      [0.95, 1.02],
      [0.98, 1.26],
      [0.94, 1.45],
      [0.84, 1.64],
      [0.68, 1.81],
      [0.47, 1.96],
      [0.24, 2.055],
      [0.08, 2.09],
      [0, 2.1],
    ].map(([radius, y]) => new THREE.Vector2(radius, y));
    const smoothProfile = new THREE.SplineCurve(glassProfile).getPoints(96);
    const glassGeometry = new THREE.LatheGeometry(smoothProfile, 96);

    const glass = new THREE.Mesh(
      glassGeometry,
      new THREE.MeshPhysicalMaterial({
        color: 0xd8e8ec,
        metalness: 0.04,
        roughness: 0.075,
        transmission: 0.94,
        thickness: 0.16,
        ior: 1.48,
        transparent: true,
        opacity: 0.32,
        depthWrite: false,
        envMapIntensity: 1.45,
      }),
    );
    model.add(glass);

    const innerGlass = new THREE.Mesh(
      glassGeometry,
      new THREE.MeshPhysicalMaterial({
        color: 0xffc76a,
        roughness: 0.22,
        transmission: 0.16,
        thickness: 0.08,
        transparent: true,
        opacity: 0.12,
        side: THREE.BackSide,
        depthWrite: false,
      }),
    );
    innerGlass.scale.setScalar(0.965);
    innerGlass.material.color.setHex(0x7e8990);
    model.add(innerGlass);

    const globeGlow = new THREE.Mesh(
      glassGeometry,
      new THREE.MeshBasicMaterial({
        color: 0x96a9b0,
        transparent: true,
        opacity: 0.035,
        depthWrite: false,
        side: THREE.BackSide,
        blending: THREE.AdditiveBlending,
      }),
    );
    globeGlow.scale.setScalar(0.93);
    model.add(globeGlow);

    const metal = new THREE.MeshStandardMaterial({
      color: 0xb5b8af,
      metalness: 0.88,
      roughness: 0.23,
      envMapIntensity: 1.7,
    });
    const darkMetal = new THREE.MeshStandardMaterial({
      color: 0x454a49,
      metalness: 0.8,
      roughness: 0.3,
    });
    const ceramic = new THREE.MeshStandardMaterial({
      color: 0x26292a,
      metalness: 0.48,
      roughness: 0.28,
    });

    function addWire(points, radius, material) {
      const curve = new THREE.CatmullRomCurve3(
        points.map(([x, y, z]) => new THREE.Vector3(x, y, z)),
      );
      const wire = new THREE.Mesh(
        new THREE.TubeGeometry(
          curve,
          Math.max(points.length * 8, 24),
          radius,
          8,
          false,
        ),
        material,
      );
      model.add(wire);
      return wire;
    }

    const screwCore = new THREE.Mesh(
      new THREE.CylinderGeometry(0.39, 0.39, 0.96, 96),
      metal,
    );
    screwCore.position.y = -0.62;
    model.add(screwCore);

    const threadPoints = [];
    const threadTurns = 5.25;
    for (let index = 0; index <= threadTurns * 20; index += 1) {
      const progress = index / (threadTurns * 20);
      const angle = progress * threadTurns * Math.PI * 2;
      threadPoints.push([
        Math.cos(angle) * 0.405,
        -1.08 + progress * 0.92,
        Math.sin(angle) * 0.405,
      ]);
    }
    addWire(threadPoints, 0.027, metal);

    const collar = new THREE.Mesh(
      new THREE.CylinderGeometry(0.4, 0.34, 0.14, 64),
      darkMetal,
    );
    collar.position.y = -1.19;
    model.add(collar);

    const contact = new THREE.Mesh(
      new THREE.SphereGeometry(0.13, 32, 20),
      metal,
    );
    contact.scale.set(1, 0.44, 1);
    contact.position.y = -1.29;
    model.add(contact);

    const socket = new THREE.Mesh(
      new THREE.CylinderGeometry(0.52, 0.62, 0.19, 64, 1),
      ceramic,
    );
    socket.position.y = -1.44;
    model.add(socket);

    for (const y of [-1.36, -1.51]) {
      const rim = new THREE.Mesh(
        new THREE.TorusGeometry(0.51, 0.018, 10, 64),
        metal,
      );
      rim.rotation.x = Math.PI / 2;
      rim.position.y = y;
      model.add(rim);
    }

    const supportMaterial = new THREE.MeshStandardMaterial({
      color: 0xb0b2a8,
      metalness: 0.7,
      roughness: 0.28,
    });
    addWire([[-0.22, -0.14, 0], [-0.18, 0.28, 0], [-0.13, 0.55, 0]], 0.014, supportMaterial);
    addWire([[0.22, -0.14, 0], [0.18, 0.28, 0], [0.13, 0.55, 0]], 0.014, supportMaterial);
    addWire([[0, -0.12, 0], [0, 0.38, 0], [0, 0.58, 0]], 0.017, supportMaterial);

    const coilPoints = [];
    const coilTurns = 11;
    for (let index = 0; index <= coilTurns * 12; index += 1) {
      const progress = index / (coilTurns * 12);
      const angle = progress * coilTurns * Math.PI * 2;
      coilPoints.push([
        -0.15 + progress * 0.3,
        0.63 + Math.sin(angle) * 0.036,
        Math.cos(angle) * 0.036,
      ]);
    }
    const filamentMaterial = new THREE.MeshStandardMaterial({
      color: 0x9c6733,
      emissive: 0x2d1504,
      emissiveIntensity: 0.2,
      metalness: 0.24,
      roughness: 0.3,
    });
    const filament = addWire(coilPoints, 0.012, filamentMaterial);

    let targetX = 0;
    let targetY = 0;
    let frame = 0;
    const render = () => {
      frame = 0;
      model.rotation.x += (targetX - model.rotation.x) * 0.12;
      model.rotation.y += (targetY - model.rotation.y) * 0.12;
      renderer.render(scene, camera);
      if (
        Math.abs(targetX - model.rotation.x) > 0.001 ||
        Math.abs(targetY - model.rotation.y) > 0.001
      ) {
        scheduleRender();
      }
    };
    const scheduleRender = () => {
      if (!frame && !document.hidden) {
        frame = requestAnimationFrame(render);
      }
    };

    const resize = () => {
      const bounds = host.getBoundingClientRect();
      if (!bounds.width || !bounds.height) {
        return;
      }
      renderer.setSize(bounds.width, bounds.height, false);
      camera.aspect = bounds.width / bounds.height;
      camera.updateProjectionMatrix();
      scheduleRender();
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);
    resize();

    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const pointerMove = (event) => {
      if (motionPreference.matches) {
        return;
      }
      const bounds = host.getBoundingClientRect();
      targetY = ((event.clientX - bounds.left) / bounds.width - 0.5) * 0.16;
      targetX = ((event.clientY - bounds.top) / bounds.height - 0.5) * -0.12;
      scheduleRender();
    };
    const pointerLeave = () => {
      targetX = 0;
      targetY = 0;
      scheduleRender();
    };
    host.addEventListener("pointermove", pointerMove);
    host.addEventListener("pointerleave", pointerLeave);

    const visibilityChange = () => {
      if (document.hidden) {
        cancelAnimationFrame(frame);
        frame = 0;
      } else {
        scheduleRender();
      }
    };
    document.addEventListener("visibilitychange", visibilityChange);

    const syncState = () => {
      const isOn = host.classList.contains("is-on");
      filamentMaterial.emissive.setHex(isOn ? 0xff8a16 : 0x2d1504);
      filamentMaterial.emissiveIntensity = isOn ? 6 : 0.2;
      filamentMaterial.color.setHex(isOn ? 0xffe7a3 : 0x9c6733);
      filamentLight.intensity = isOn ? 7.5 : 0;
      filamentLight.distance = isOn ? 4.2 : 0.1;
      glass.material.color.setHex(isOn ? 0xffd28a : 0xd8e8ec);
      glass.material.roughness = isOn ? 0.11 : 0.075;
      globeGlow.material.color.setHex(isOn ? 0xffae4d : 0x96a9b0);
      globeGlow.material.opacity = isOn ? 0.14 : 0.035;
      scheduleRender();
    };
    const stateObserver = new MutationObserver(syncState);
    stateObserver.observe(host, { attributes: true, attributeFilter: ["class"] });
    syncState();
    host.classList.add("has-webgl");

    window.addEventListener(
      "pagehide",
      () => {
        cancelAnimationFrame(frame);
        resizeObserver.disconnect();
        stateObserver.disconnect();
        host.removeEventListener("pointermove", pointerMove);
        host.removeEventListener("pointerleave", pointerLeave);
        document.removeEventListener("visibilitychange", visibilityChange);
        environment.dispose();
        renderer.dispose();
      },
      { once: true },
    );
  } catch (error) {
    console.error("3D電球を初期化できませんでした。SVG表示に切り替えます。", error);
  }
}
