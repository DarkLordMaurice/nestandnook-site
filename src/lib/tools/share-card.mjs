/**
 * share-card.mjs
 * Shared canvas-based "shareable result card" renderer for Nest & Nook tools.
 * Produces a 1248x832 (3:2 landscape) downloadable PNG.
 *
 * Added 2026-07-16 per Maurice's explicit request that tool results include
 * "something shareable they receive at the end like an info graphic or
 * certificate" — the 2 pre-existing tools (space-and-the-stars,
 * your-small-space-personality) only ever had a "copy result text to
 * clipboard" share action; this is a genuine step up, not a retrofit of
 * that pattern.
 *
 * Rebuilt 2026-07-16 (same day, later) to resolve a real contradiction: the
 * first version of this file was a flat-color 1080x1080 SQUARE card, built
 * before `scripts/gen_certificate_frames.py` was written a few hours later
 * establishing the actual direction — a LANDSCAPE (3:2), photographic
 * flat-lay "certificate" background with result text composited on top,
 * never a flat illustrated square. Maurice confirmed landscape is correct
 * (2026-07-16) after this was flagged as an unresolved contradiction between
 * the two files. This version now matches `gen_certificate_frames.py`'s
 * 1248x832 output exactly and draws the real generated frame image as the
 * background when one exists for that tool (`frameSrc`), compositing text
 * into the deliberately-left-blank region of the frame rather than over a
 * flat color band.
 *
 * Only one frame currently exists on disk:
 * `/winnie/cert-frame-why-doesnt-this-feel-done-yet.jpg`. The other two
 * tools (regret-proof-purchase-check, roast-my-space) don't have a
 * generated frame yet — calling without `frameSrc` (or if the image fails
 * to load) falls back to a flat cream-parchment background so the card
 * still renders correctly today; swap in a real `frameSrc` for those two
 * the moment their frames are generated, no other code change needed.
 *
 * Pure JS — no imports beyond the native Image/Canvas APIs, no network
 * calls except loading the frame image itself (same-origin, from /winnie/).
 */

const PALETTE = {
  cream: '#faf4e8',
  ink: '#2c2418',
  inkSoft: '#5a4f40',
  terracotta: '#c1602e',
  sage: '#7c8b6f',
  border: '#e7dbc4',
  jewelTeal: '#123a37',
  gold: '#c9a227',
  creamOnDark: '#f6ecd6',
};

function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
  const words = String(text ?? '').split(' ');
  const lines = [];
  let line = '';
  for (const word of words) {
    const test = line ? `${line} ${word}` : word;
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line);
      line = word;
    } else {
      line = test;
    }
  }
  if (line) lines.push(line);
  lines.forEach((l, i) => ctx.fillText(l, x, y + i * lineHeight));
  return lines.length * lineHeight;
}

const FRAME_WIDTH = 1248;
const FRAME_HEIGHT = 832;

function loadImage(src) {
  return new Promise((resolve, reject) => {
    if (!src) {
      reject(new Error('no frameSrc supplied'));
      return;
    }
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`failed to load frame image: ${src}`));
    img.src = src;
  });
}

// Draws `img` covering the full width/height (like CSS object-fit: cover),
// center-cropping whichever axis overshoots.
function drawCoverImage(ctx, img, width, height) {
  const imgRatio = img.width / img.height;
  const boxRatio = width / height;
  let drawWidth, drawHeight, dx, dy;
  if (imgRatio > boxRatio) {
    drawHeight = height;
    drawWidth = height * imgRatio;
    dx = (width - drawWidth) / 2;
    dy = 0;
  } else {
    drawWidth = width;
    drawHeight = width / imgRatio;
    dx = 0;
    dy = (height - drawHeight) / 2;
  }
  ctx.drawImage(img, dx, dy, drawWidth, drawHeight);
}

/**
 * Draw a shareable result card onto a canvas. Async because it may need to
 * load the background frame image first.
 * @param {HTMLCanvasElement} canvas
 * @param {{ kicker: string, headline: string, body: string, footerLine?: string, frameSrc?: string }} opts
 *   frameSrc — path to a generated landscape certificate-frame photo (see
 *   scripts/gen_certificate_frames.py). Omit or leave unset for a tool that
 *   doesn't have one generated yet; falls back to a flat cream card.
 */
export async function renderShareCard(canvas, { kicker, headline, body, footerLine, frameSrc }) {
  canvas.width = FRAME_WIDTH;
  canvas.height = FRAME_HEIGHT;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  let hasFrame = false;
  if (frameSrc) {
    try {
      const img = await loadImage(frameSrc);
      drawCoverImage(ctx, img, FRAME_WIDTH, FRAME_HEIGHT);
      hasFrame = true;
    } catch {
      hasFrame = false; // fall through to the flat fallback below
    }
  }

  if (!hasFrame) {
    // Flat cream-parchment fallback for tools without a generated frame yet
    // (currently: regret-proof-purchase-check, roast-my-space).
    ctx.fillStyle = PALETTE.cream;
    ctx.fillRect(0, 0, FRAME_WIDTH, FRAME_HEIGHT);
    ctx.strokeStyle = PALETTE.border;
    ctx.lineWidth = 3;
    ctx.strokeRect(20, 20, FRAME_WIDTH - 40, FRAME_HEIGHT - 40);
  }

  // Safe content column. Keeps every line of text away from the frame's own
  // reserved corners — a tape measure in the bottom-left and a pencil in the
  // upper-right, per gen_certificate_frames.py's composition notes — by
  // sitting entirely inside the deliberately-left-blank middle/right region
  // the frame photo was generated to leave open.
  const contentX = 380;
  const contentWidth = FRAME_WIDTH - 70 - contentX;

  ctx.fillStyle = PALETTE.terracotta;
  ctx.font = '600 22px Georgia, "Iowan Old Style", serif';
  ctx.fillText('NEST & NOOK', contentX, 110);
  ctx.fillStyle = PALETTE.inkSoft;
  ctx.font = '400 18px Georgia, serif';
  ctx.fillText('nestandnook.org', contentX, 136);

  // Kicker + gold rule
  ctx.fillStyle = PALETTE.terracotta;
  ctx.font = '700 22px Georgia, serif';
  ctx.fillText(String(kicker ?? '').toUpperCase(), contentX, 192);
  ctx.strokeStyle = PALETTE.gold;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(contentX, 210);
  ctx.lineTo(contentX + 140, 210);
  ctx.stroke();

  // Headline
  ctx.fillStyle = PALETTE.ink;
  ctx.font = '700 46px Georgia, "Iowan Old Style", serif';
  const headlineHeight = wrapText(ctx, headline, contentX, 272, contentWidth, 52);

  // Body
  ctx.fillStyle = PALETTE.inkSoft;
  ctx.font = '400 25px Arial, "Segoe UI", sans-serif';
  wrapText(ctx, body, contentX, 272 + headlineHeight + 44, contentWidth, 35);

  // Footer
  ctx.fillStyle = PALETTE.sage;
  ctx.font = 'italic 400 21px Georgia, serif';
  ctx.fillText(footerLine || 'Try it yourself at nestandnook.org/tools/', contentX, FRAME_HEIGHT - 90);
}

/**
 * Trigger a PNG download of the given canvas.
 * @param {HTMLCanvasElement} canvas
 * @param {string} filename
 */
export function downloadCanvas(canvas, filename) {
  canvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, 'image/png');
}
