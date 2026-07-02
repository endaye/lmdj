const canvas = document.getElementById("dotCanvas");
const input = document.getElementById("textInput");
const ctx = canvas.getContext("2d", { alpha: false });

const maskCanvas = document.createElement("canvas");
const maskCtx = maskCanvas.getContext("2d", { willReadFrequently: true });

input.value = "";

const glyphs =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#$%&*+-/<>=[]{}()@!?;:,.";

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
  text: input.value,
  mask: null,
  lastTime: performance.now(),
};

function resize() {
  state.dpr = Math.min(window.devicePixelRatio || 1, 2);
  state.width = window.innerWidth;
  state.height = window.innerHeight;
  state.cell = state.width < 640 ? 13 : 16;
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
  buildTextMask();
}

function buildStreams() {
  state.streams = Array.from({ length: state.columns }, (_, index) => ({
    head: Math.random() * state.rows,
    speed: 3.2 + Math.random() * 9.5,
    length: 7 + Math.floor(Math.random() * 18),
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

function buildTextMask() {
  const text = state.text.trim();
  if (!text) {
    state.mask = null;
    return;
  }

  maskCanvas.width = state.columns;
  maskCanvas.height = state.rows;
  maskCtx.clearRect(0, 0, maskCanvas.width, maskCanvas.height);

  const maxTextWidth = Math.max(8, state.columns * 0.82);
  const maxTextHeight = Math.max(5, state.rows * 0.46);
  const fontSize = fitMaskFontSize(text, maxTextWidth, maxTextHeight);
  const lines = wrapMaskText(text, maxTextWidth, fontSize);
  const lineHeight = fontSize * 1.08;
  const blockHeight = lines.length * lineHeight;
  const centerY = state.rows * 0.37;
  const firstY = centerY - blockHeight / 2 + lineHeight / 2;

  maskCtx.fillStyle = "#fff";
  maskCtx.textAlign = "center";
  maskCtx.textBaseline = "middle";
  maskCtx.font = `900 ${fontSize}px Arial Black, Impact, sans-serif`;

  for (let i = 0; i < lines.length; i += 1) {
    maskCtx.fillText(lines[i], state.columns / 2, firstY + i * lineHeight);
  }

  const data = maskCtx.getImageData(0, 0, state.columns, state.rows).data;
  const mask = new Uint8Array(state.columns * state.rows);

  for (let y = 0; y < state.rows; y += 1) {
    for (let x = 0; x < state.columns; x += 1) {
      const alpha = data[(y * state.columns + x) * 4 + 3];
      mask[y * state.columns + x] = alpha > 24 ? alpha : 0;
    }
  }

  state.mask = mask;
}

function fitMaskFontSize(text, maxWidth, maxHeight) {
  let low = 3;
  let high = Math.max(8, Math.floor(state.columns * 0.22));
  let best = low;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    maskCtx.font = `900 ${mid}px Arial Black, Impact, sans-serif`;
    const lines = wrapMaskText(text, maxWidth, mid);
    const widest = Math.max(...lines.map((line) => maskCtx.measureText(line).width));
    const totalHeight = lines.length * mid * 1.08;

    if (widest <= maxWidth && totalHeight <= maxHeight) {
      best = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  return best;
}

function wrapMaskText(text, maxWidth) {
  const normalized = text.toUpperCase().replace(/\s+/g, " ").trim();
  if (!normalized) return [""];

  const tokens = normalized.includes(" ") ? normalized.split(" ") : Array.from(normalized);
  const keepSpaces = normalized.includes(" ");
  const lines = [];
  let current = "";

  for (const token of tokens) {
    const candidate = keepSpaces && current ? `${current} ${token}` : `${current}${token}`;
    if (current && maskCtx.measureText(candidate).width > maxWidth) {
      lines.push(current);
      current = token;
    } else {
      current = candidate;
    }
  }

  if (current) lines.push(current);
  return lines;
}

function render(now) {
  const dt = Math.min(0.05, (now - state.lastTime) / 1000);
  state.lastTime = now;

  ctx.fillStyle = "rgba(0, 0, 0, 0.2)";
  ctx.fillRect(0, 0, state.width, state.height);

  updateStreams(dt);
  drawRain(now);
  if (state.mask) drawTextSignal(now);

  requestAnimationFrame(render);
}

function updateStreams(dt) {
  for (const stream of state.streams) {
    stream.head += stream.speed * dt;
    if (stream.head - stream.length > state.rows + stream.delay) {
      stream.head = -Math.random() * state.rows * 0.35;
      stream.speed = 3.2 + Math.random() * 9.5;
      stream.length = 7 + Math.floor(Math.random() * 18);
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
      const glowAlpha = Math.min(0.55, strength * 0.36);

      ctx.fillStyle = `rgba(0, 255, 102, ${glowAlpha})`;
      ctx.fillRect(x * state.cell, y * state.cell, state.cell, state.cell);
      ctx.fillStyle = `rgba(238, 255, 242, ${Math.min(1, 0.72 + strength * 0.28)})`;
      ctx.fillText(getGlyph(x, y), px, py);
    }
  }
}

function getGlyph(column, row) {
  return state.glyphGrid[column]?.[row] || randomGlyph();
}

function randomGlyph() {
  return glyphs[Math.floor(Math.random() * glyphs.length)];
}

input.addEventListener("input", () => {
  state.text = input.value;
  buildTextMask();
});

window.addEventListener("resize", resize);

resize();
requestAnimationFrame(render);
