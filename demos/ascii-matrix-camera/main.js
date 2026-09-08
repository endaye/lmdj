const canvas = document.getElementById("dotCanvas");
const cameraButton = document.getElementById("cameraButton");
const ctx = canvas.getContext("2d", { alpha: false });

const maskCanvas = document.createElement("canvas");
const maskCtx = maskCanvas.getContext("2d", { willReadFrequently: true });
const catImage = new Image();
const cameraCanvas = document.createElement("canvas");
const cameraCtx = cameraCanvas.getContext("2d", { willReadFrequently: true });
const cameraVideo = document.createElement("video");

catImage.src = "./assets/cat.png";
cameraVideo.muted = true;
cameraVideo.playsInline = true;

const glyphs =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#$%&*+-/<>=[]{}()@!?;:,.";
const toneGlyphs = ".,:;irsXA253hMHGS#9B&@";

const state = {
  width: 0,
  height: 0,
  dpr: 1,
  cell: 16,
  fontSize: 16,
  columns: 0,
  rows: 0,
  streams: [],
  glyphGrid: [],
  mask: null,
  maskKind: "image",
  cameraActive: false,
  cameraReady: false,
  cameraError: "",
  lastTime: performance.now(),
};

window.asciiCameraState = state;

function resize() {
  state.dpr = Math.min(window.devicePixelRatio || 1, 2);
  state.width = window.innerWidth;
  state.height = window.innerHeight;
  state.cell = state.width < 640 ? 9 : 9;
  state.fontSize = state.cell;
  state.columns = Math.ceil(state.width / state.cell);
  state.rows = Math.ceil(state.height / state.cell);

  canvas.width = Math.floor(state.width * state.dpr);
  canvas.height = Math.floor(state.height * state.dpr);
  canvas.style.width = `${state.width}px`;
  canvas.style.height = `${state.height}px`;
  ctx.setTransform(state.dpr, 0, 0, state.dpr, 0, 0);
  ctx.font = `${state.fontSize}px "SFMono-Regular", "SF Mono", Consolas, monospace`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  buildStreams();
  buildGlyphGrid();
  buildSignalMask();
}

function buildStreams() {
  state.streams = Array.from({ length: state.columns }, (_, index) => ({
    head: Math.random() * state.rows,
    speed: 5.2 + Math.random() * 14,
    length: 12 + Math.floor(Math.random() * 28),
    delay: Math.random() * state.rows,
    phase: Math.random() * Math.PI * 2,
    column: index,
  }));
}

function buildGlyphGrid() {
  state.glyphGrid = Array.from({ length: state.columns }, () =>
    Array.from({ length: state.rows }, () => randomGlyph()),
  );
}

function buildSignalMask() {
  if (state.cameraReady) {
    buildCameraMask();
    return;
  }

  buildImageMask();
}

function buildImageMask() {
  if (!catImage.complete || !catImage.naturalWidth) {
    state.mask = null;
    state.maskKind = "image";
    return;
  }

  maskCanvas.width = state.columns;
  maskCanvas.height = state.rows;
  maskCtx.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
  maskCtx.imageSmoothingEnabled = true;
  maskCtx.imageSmoothingQuality = "high";

  const maxImageWidth = state.columns * 0.88;
  const maxImageHeight = state.rows * 0.78;
  const scale = Math.min(
    maxImageWidth / catImage.naturalWidth,
    maxImageHeight / catImage.naturalHeight,
  );
  const drawWidth = Math.max(1, catImage.naturalWidth * scale);
  const drawHeight = Math.max(1, catImage.naturalHeight * scale);
  const drawX = (state.columns - drawWidth) / 2;
  const drawY = state.rows * 0.42 - drawHeight / 2;

  maskCtx.drawImage(catImage, drawX, drawY, drawWidth, drawHeight);

  const data = maskCtx.getImageData(0, 0, state.columns, state.rows).data;
  const mask = new Uint8Array(state.columns * state.rows);

  for (let y = 0; y < state.rows; y += 1) {
    for (let x = 0; x < state.columns; x += 1) {
      const index = (y * state.columns + x) * 4;
      const r = data[index];
      const g = data[index + 1];
      const b = data[index + 2];
      const a = data[index + 3] / 255;
      const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      const chroma = Math.max(r, g, b) - Math.min(r, g, b);
      const isCatPixel = a > 0.1 && (luminance > 12 || chroma > 18);

      if (isCatPixel) {
        const maskIndex = y * state.columns + x;
        mask[maskIndex] = Math.max(28, Math.min(255, luminance * 1.04 + chroma * 0.24));
      }
    }
  }

  state.mask = mask;
  state.maskKind = "image";
}

function buildCameraMask() {
  if (!cameraVideo.videoWidth || !cameraVideo.videoHeight) {
    state.mask = null;
    state.maskKind = "camera";
    return;
  }

  cameraCanvas.width = state.columns;
  cameraCanvas.height = state.rows;
  cameraCtx.save();
  cameraCtx.clearRect(0, 0, cameraCanvas.width, cameraCanvas.height);

  const maxCameraWidth = state.columns * 0.74;
  const maxCameraHeight = state.rows * 0.7;
  const scale = Math.min(
    maxCameraWidth / cameraVideo.videoWidth,
    maxCameraHeight / cameraVideo.videoHeight,
  );
  const drawWidth = Math.max(1, cameraVideo.videoWidth * scale);
  const drawHeight = Math.max(1, cameraVideo.videoHeight * scale);
  const drawX = (state.columns - drawWidth) / 2;
  const drawY = state.rows * 0.42 - drawHeight / 2;

  cameraCtx.translate(drawX + drawWidth, drawY);
  cameraCtx.scale(-1, 1);
  cameraCtx.drawImage(cameraVideo, 0, 0, drawWidth, drawHeight);
  cameraCtx.restore();

  const data = cameraCtx.getImageData(0, 0, state.columns, state.rows).data;
  const mask = new Uint8Array(state.columns * state.rows);

  for (let y = 0; y < state.rows; y += 1) {
    for (let x = 0; x < state.columns; x += 1) {
      const index = (y * state.columns + x) * 4;
      const r = data[index];
      const g = data[index + 1];
      const b = data[index + 2];
      const contrasted = {
        r: bound((r - 128) * 1.65 + 128, 0, 255),
        g: bound((g - 128) * 1.65 + 128, 0, 255),
        b: bound((b - 128) * 1.65 + 128, 0, 255),
      };
      const luminance = 0.299 * contrasted.r + 0.587 * contrasted.g + 0.114 * contrasted.b;

      if (luminance > 18) {
        mask[y * state.columns + x] = Math.max(20, Math.min(255, luminance));
      }
    }
  }

  state.mask = mask;
  state.maskKind = "camera";
}

function render(now) {
  const dt = Math.min(0.05, (now - state.lastTime) / 1000);
  state.lastTime = now;

  ctx.fillStyle = "rgba(0, 0, 0, 0.2)";
  ctx.fillRect(0, 0, state.width, state.height);

  updateStreams(dt);
  if (state.cameraReady) buildCameraMask();
  drawRain(now);
  if (state.mask) drawTextSignal(now);

  requestAnimationFrame(render);
}

function updateStreams(dt) {
  for (const stream of state.streams) {
    stream.head += stream.speed * dt;
    if (stream.head - stream.length > state.rows + stream.delay) {
      stream.head = -Math.random() * state.rows * 0.35;
      stream.speed = 5.2 + Math.random() * 14;
      stream.length = 12 + Math.floor(Math.random() * 28);
      stream.delay = Math.random() * state.rows * 0.35;
    }
  }
}

function drawRain(now) {
  for (const stream of state.streams) {
    const x = stream.column * state.cell + state.cell / 2;
    const head = Math.floor(stream.head);

    for (let trail = 0; trail < stream.length; trail += 1) {
      const row = head - trail;
      if (row < 0 || row >= state.rows) continue;

      const y = row * state.cell + state.cell / 2;
      const fade = 1 - trail / stream.length;
      const pulse = Math.sin(now * 0.003 + stream.phase + trail * 0.31) * 0.08;
      const alpha = Math.max(0.04, fade * 0.72 + pulse);

      ctx.fillStyle =
        trail === 0
          ? "rgba(230, 255, 238, 0.95)"
          : `rgba(0, 255, 102, ${alpha})`;
      ctx.fillText(getGlyph(stream.column, row), x, y);
    }
  }
}

function drawTextSignal(now) {
  const flicker = 0.9 + Math.sin(now * 0.006) * 0.08;

  for (let y = 0; y < state.rows; y += 1) {
    for (let x = 0; x < state.columns; x += 1) {
      const maskValue = state.mask[y * state.columns + x];
      if (!maskValue) continue;

      const px = x * state.cell + state.cell / 2;
      const py = y * state.cell + state.cell / 2;
      const strength = (maskValue / 255) * flicker;
      const glyphAlpha = Math.min(1, 0.16 + strength * 0.84);
      ctx.fillStyle = `rgba(0, 255, 102, ${glyphAlpha})`;
      ctx.fillText(getToneGlyph(maskValue), px, py);
    }
  }
}

function getGlyph(column, row) {
  return state.glyphGrid[column]?.[row] || randomGlyph();
}

function randomGlyph() {
  return glyphs[Math.floor(Math.random() * glyphs.length)];
}

function getToneGlyph(value) {
  const index = Math.max(0, Math.min(toneGlyphs.length - 1, Math.floor((value / 255) * toneGlyphs.length)));
  return toneGlyphs[index];
}

function bound(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    state.cameraError = "Camera API is not supported.";
    cameraButton.textContent = "NO";
    return;
  }

  try {
    cameraButton.textContent = "...";
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: "user",
        width: { ideal: 640 },
        height: { ideal: 480 },
      },
      audio: false,
    });
    cameraVideo.srcObject = stream;
    await cameraVideo.play();
    state.cameraActive = true;
    state.cameraReady = true;
    state.cameraError = "";
    cameraButton.textContent = "CAM";
    cameraButton.classList.add("is-active");
    buildSignalMask();
  } catch (error) {
    state.cameraActive = false;
    state.cameraReady = false;
    state.cameraError = error instanceof Error ? error.message : "Camera failed.";
    cameraButton.textContent = "OFF";
    cameraButton.title = state.cameraError;
    cameraButton.classList.remove("is-active");
    buildSignalMask();
  }
}
window.addEventListener("resize", resize);
catImage.addEventListener("load", buildSignalMask);
cameraButton.addEventListener("click", startCamera);

resize();
requestAnimationFrame(render);
