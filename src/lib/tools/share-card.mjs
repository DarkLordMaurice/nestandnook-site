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
 * All 5 lifestyle/personality tools now have a generated frame on disk
 * (`/winnie/cert-frame-{tool-slug}.jpg`, see scripts/gen_certificate_frames.py) —
 * calling without `frameSrc` (or if the image fails to load) still falls
 * back to a flat cream-parchment background as a safety net.
 *
 * 2026-07-18: added `openBlankTab` / `showCanvasInTab` as the standard way
 * to present the finished card. Maurice was explicit that a forced disk
 * download on click was the wrong UX — the certificate should open in a
 * new tab like any other image, with saving left as something the person
 * does themselves from there (right-click → save, or the browser's own
 * image-view controls), not something forced on them. `downloadCanvas`
 * still exists below in case a real "download" button is wanted
 * deliberately somewhere, but none of the tool pages call it anymore.
 *
 * REBUILT 2026-07-18 (same day, later): the version above shipped with two
 * real problems Maurice caught from a live screenshot. First, it never used
 * the text-layout reference he'd given earlier in the certificate work (a
 * finished Scorpio card showing: eyebrow line, glyph beside the headline, a
 * pill-shaped subtitle badge, a body paragraph, a two-column boxed callout,
 * and a "Winnie says" quote line) — the old renderer only ever drew four
 * generic blocks (kicker/headline/body/footer) and threw away data (each
 * result's superpower/kryptonite/Winnie quote) that was sitting right there
 * in the page already. Second, and worse: the old `contentX = 380` fixed
 * column was tuned for a completely different frame concept from months
 * earlier (a tape-measure/pencil corner layout) and was never re-checked
 * against the real certificate borders' actual blank-center rectangle —
 * text overflowed past the frame edges and clashed with the ornamentation.
 * This rebuild fixes both: it draws the full Scorpio-reference hierarchy,
 * and every tool now passes an explicit `contentBox` (measured directly off
 * that tool's real cert-frame-*.jpg blank rectangle — see the `x`, `y`,
 * `width`, `height` values in each tools/*.astro call) so text is
 * guaranteed to stay inside that frame's actual open area. All text sizing
 * inside `renderShareCard` auto-shrinks to fit the given box rather than
 * assuming a fixed size will always fit, since the 5 frames' open areas are
 * not identical (they're independently generated images, not a template).
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

// Splits `text` into wrapped lines that fit `maxWidth` under ctx's current
// font, WITHOUT drawing anything — used by the auto-fit sizing pass below.
function measureWrappedLines(ctx, text, maxWidth) {
  const words = String(text ?? '').split(' ').filter(Boolean);
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
  return lines;
}

function drawWrappedLines(ctx, lines, x, y, lineHeight, align = 'left') {
  const prevAlign = ctx.textAlign;
  if (align) ctx.textAlign = align;
  lines.forEach((l, i) => ctx.fillText(l, x, y + i * lineHeight));
  ctx.textAlign = prevAlign;
  return lines.length * lineHeight;
}

// Finds the largest font size (stepping down from `maxSize` to `minSize`)
// at which `text` wraps into no more than `maxLines` lines at `maxWidth`.
// Prevents the overflow bug that shipped 2026-07-18: rather than assuming a
// fixed font size always fits, every variable-length field is measured
// first and shrunk until it provably fits its box.
function fitFontSize(ctx, text, weightFamily, maxWidth, maxLines, maxSize, minSize) {
  for (let size = maxSize; size >= minSize; size -= 1) {
    ctx.font = `${weightFamily} ${size}px Georgia, "Iowan Old Style", serif`;
    const lines = measureWrappedLines(ctx, text, maxWidth);
    if (lines.length <= maxLines) return { size, lines };
  }
  ctx.font = `${weightFamily} ${minSize}px Georgia, "Iowan Old Style", serif`;
  let lines = measureWrappedLines(ctx, text, maxWidth);
  if (lines.length > maxLines) {
    lines = lines.slice(0, maxLines);
    const last = lines[maxLines - 1];
    while (ctx.measureText(`${last}…`).width > maxWidth && last.length > 1) {
      lines[maxLines - 1] = lines[maxLines - 1].slice(0, -1);
    }
    lines[maxLines - 1] = `${lines[maxLines - 1]}…`;
  }
  return { size: minSize, lines };
}

// Small hand-drawn line-art glyphs for the 4 tools that don't have a
// zodiac-style unicode character of their own (space-and-the-stars uses the
// real sign glyph instead, e.g. "♏", drawn as text). Matches the same icon
// already engraved into that tool's certificate border, per Maurice's call
// on 2026-07-18 ("match the border's own motif"). Drawn as simple vector
// line art rather than emoji so it stays in the gold/ink line-art style
// instead of switching to a colored emoji font partway through the card.
function drawGlyphIcon(ctx, type, cx, cy, size, color) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = Math.max(2, size * 0.07);
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  const s = size / 2;

  if (type === 'house') {
    ctx.beginPath();
    ctx.moveTo(cx - s, cy + s * 0.15);
    ctx.lineTo(cx, cy - s);
    ctx.lineTo(cx + s, cy + s * 0.15);
    ctx.stroke();
    ctx.strokeRect(cx - s * 0.7, cy + s * 0.1, s * 1.4, s * 0.9);
    ctx.fillRect(cx - s * 0.18, cy + s * 0.55, s * 0.36, s * 0.45);
  } else if (type === 'magnifier') {
    ctx.beginPath();
    ctx.arc(cx - s * 0.15, cy - s * 0.15, s * 0.55, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + s * 0.25, cy + s * 0.25);
    ctx.lineTo(cx + s * 0.75, cy + s * 0.75);
    ctx.stroke();
  } else if (type === 'flame') {
    ctx.beginPath();
    ctx.moveTo(cx, cy - s);
    ctx.bezierCurveTo(cx + s * 0.75, cy - s * 0.2, cx + s * 0.5, cy + s * 0.3, cx, cy + s);
    ctx.bezierCurveTo(cx - s * 0.5, cy + s * 0.3, cx - s * 0.75, cy - s * 0.2, cx, cy - s);
    ctx.closePath();
    ctx.fill();
  } else if (type === 'dollar') {
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `700 ${size}px Georgia, "Iowan Old Style", serif`;
    ctx.fillText('$', cx, cy + size * 0.05);
    ctx.textBaseline = 'alphabetic';
  }
  ctx.restore();
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
 *
 * Layout matches the reference Maurice provided (a finished Space & the
 * Stars / Scorpio card): eyebrow line → glyph beside the headline → pill
 * subtitle badge → body paragraph → two-column (or one-column) boxed
 * callout → "Winnie says" quote line → footer.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {object} opts
 * @param {string} opts.kicker - eyebrow line, e.g. "YOUR SPACE SIGN"
 * @param {string} opts.headline - big headline, e.g. the archetype/type name
 * @param {{type: 'text'|'house'|'magnifier'|'flame'|'dollar', value?: string}} [opts.glyph]
 *   - glyph shown to the left of the headline. type:'text' draws opts.glyph.value
 *   (e.g. a real zodiac character) in the headline font; the other types draw
 *   a small hand-drawn line-art icon matching that tool's certificate border motif.
 * @param {string} [opts.badge] - short pill-badge subtitle under the headline
 * @param {string} opts.body - main descriptive paragraph
 * @param {{label: string, value: string}[]} [opts.columns] - 1 or 2 boxed callouts
 * @param {string} [opts.quote] - "Winnie says" line (quote marks added automatically)
 * @param {string} [opts.footerLine]
 * @param {string} [opts.frameSrc] - path to a generated cert-frame-*.jpg (see
 *   scripts/gen_certificate_frames.py). Omit, or if the image fails to load,
 *   falls back to a flat cream card.
 * @param {{x: number, y: number, width: number, height: number}} [opts.contentBox]
 *   - the frame's actual measured blank rectangle, in canvas pixels. REQUIRED
 *   for accurate placement on a real frame — measured once per tool directly
 *   off its cert-frame-*.jpg (see each tools/*.astro call site for the
 *   values and how they were derived). Falls back to a generic centered box
 *   if omitted, for the no-frame fallback case.
 */
export async function renderShareCard(canvas, { kicker, headline, glyph, badge, body, columns, quote, footerLine, frameSrc, contentBox }) {
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
    ctx.fillStyle = PALETTE.cream;
    ctx.fillRect(0, 0, FRAME_WIDTH, FRAME_HEIGHT);
    ctx.strokeStyle = PALETTE.border;
    ctx.lineWidth = 3;
    ctx.strokeRect(20, 20, FRAME_WIDTH - 40, FRAME_HEIGHT - 40);
  }

  const box = contentBox || { x: 220, y: 220, width: FRAME_WIDTH - 440, height: FRAME_HEIGHT - 440 };
  const left = box.x;
  const right = box.x + box.width;
  const contentWidth = box.width;

  // Hard clip to the measured safe box. This is the actual fix for the
  // 2026-07-18 overflow bug: everything below is a best-effort layout that
  // tries to fit within the box, but if a particular result's text still
  // runs long, this clip guarantees it gets cut off cleanly inside the box
  // rather than bleeding onto the frame's own border artwork. A reserved
  // footer strip is carved out first and drawn in its own un-clipped pass
  // at a fixed position, so the two can never overlap regardless of how
  // long the content above happens to run.
  const footerReserve = 22;
  const availableHeight = box.height - footerReserve;

  // --- Measurement pass ---
  // Every section is sized/wrapped FIRST, with nothing drawn yet, so the
  // total content height is known before any drawing happens. This is what
  // lets the block be vertically centered inside boxes that are taller than
  // the content needs (e.g. the your-small-space-personality frame, whose
  // blank rectangle is much shorter/wider than space-and-the-stars') instead
  // of always hugging the top with a big dead gap before the fixed-position
  // footer — a real gap caught 2026-07-18 on that frame's own test render,
  // right alongside the "Winnie says" quote getting cut off mid-sentence
  // because it was hard-capped at 1 line. Quote is now allowed up to 2 lines
  // for exactly that reason; the wider space-and-the-stars frame still lets
  // most quotes sit on a single line at a larger size, so this doesn't
  // regress that box — it only gives narrower boxes the room they need.
  ctx.textAlign = 'left';

  const eyebrowH = kicker ? 26 : 0;

  const glyphSize = 40;
  let headlineX = left;
  let headlineMaxWidth = contentWidth;
  if (glyph) {
    headlineX = left + glyphSize + 14;
    headlineMaxWidth = contentWidth - glyphSize - 14;
  }
  const headlineText = String(headline ?? '');
  const { size: headlineSize, lines: headlineLines } = fitFontSize(ctx, headlineText, '700', headlineMaxWidth, 2, 34, 20);
  const headlineLineHeight = headlineSize * 1.12;
  const headlineBlockH = Math.max(headlineLineHeight * headlineLines.length, glyphSize + 6) + 10;

  let pillW = 0;
  const pillH = 23;
  const badgeLabel = badge ? String(badge).toUpperCase() : '';
  if (badge) {
    ctx.font = '700 13px Georgia, serif';
    pillW = ctx.measureText(badgeLabel).width + 28;
  }
  const badgeBlockH = badge ? pillH + 10 : 0;

  let bodySize = 0;
  let bodyLines = [];
  if (body) {
    const r = fitFontSize(ctx, body, '400', contentWidth, 3, 16, 11);
    bodySize = r.size;
    bodyLines = r.lines;
  }
  const bodyLineHeight = bodySize * 1.35;
  const bodyBlockH = body ? bodyLineHeight * bodyLines.length + 10 : 0;

  const colGap = 12;
  const colBoxH = 50;
  const colsData = [];
  if (columns && columns.length) {
    const colW = (contentWidth - colGap * (columns.length - 1)) / columns.length;
    columns.forEach((col) => {
      const r = fitFontSize(ctx, col.value ?? '', '400', colW - 18, 2, 12, 9);
      colsData.push({ label: col.label, colW, valSize: r.size, valLines: r.lines });
    });
  }
  const columnsBlockH = colsData.length ? colBoxH + 10 : 0;

  let quoteSize = 0;
  let quoteLines = [];
  if (quote) {
    const r = fitFontSize(ctx, `"${quote}"`, 'italic 400', contentWidth, 2, 14, 10);
    quoteSize = r.size;
    quoteLines = r.lines;
  }
  const quoteLineHeight = quoteSize * 1.3;
  const quoteBlockH = quote ? quoteLineHeight * quoteLines.length + 6 : 0;

  const totalContentH = eyebrowH + headlineBlockH + badgeBlockH + bodyBlockH + columnsBlockH + quoteBlockH;
  const slack = Math.max(0, availableHeight - totalContentH);
  // Only ever pushes content DOWN from the box's top edge to center it in
  // extra room — never up, and never past what clip already guards against.
  const startY = box.y + slack / 2;

  ctx.save();
  ctx.beginPath();
  ctx.rect(box.x, box.y, box.width, box.height - footerReserve);
  ctx.clip();

  let cy = startY;

  // Eyebrow line
  if (kicker) {
    ctx.fillStyle = PALETTE.terracotta;
    ctx.font = '700 17px Georgia, serif';
    ctx.fillText(String(kicker).toUpperCase(), left, cy + 14);
    cy += eyebrowH;
  }

  // Headline, with an optional glyph to its left
  if (glyph) {
    drawGlyphIcon(ctx, glyph.type, left + glyphSize / 2, cy + 22, glyphSize, PALETTE.terracotta);
    if (glyph.type === 'text' && glyph.value) {
      ctx.fillStyle = PALETTE.terracotta;
      ctx.font = `700 ${glyphSize}px Georgia, serif`;
      ctx.fillText(glyph.value, left, cy + 38);
    }
  }
  ctx.fillStyle = PALETTE.ink;
  ctx.font = `700 ${headlineSize}px Georgia, "Iowan Old Style", serif`;
  drawWrappedLines(ctx, headlineLines, headlineX, cy + headlineSize * 0.78, headlineLineHeight);
  cy += headlineBlockH;

  // Pill subtitle badge
  if (badge) {
    ctx.fillStyle = PALETTE.jewelTeal;
    ctx.beginPath();
    ctx.roundRect(left, cy, pillW, pillH, pillH / 2);
    ctx.fill();
    ctx.fillStyle = PALETTE.creamOnDark;
    ctx.font = '700 13px Georgia, serif';
    ctx.fillText(badgeLabel, left + 14, cy + pillH / 2 + 4.5);
    cy += badgeBlockH;
  }

  // Body paragraph
  if (body) {
    ctx.fillStyle = PALETTE.inkSoft;
    ctx.font = `400 ${bodySize}px Georgia, serif`;
    drawWrappedLines(ctx, bodyLines, left, cy + bodySize, bodyLineHeight);
    cy += bodyBlockH;
  }

  // Two-column (or one-column) boxed callout
  if (colsData.length) {
    colsData.forEach((col, i) => {
      const bx = left + i * (col.colW + colGap);
      ctx.strokeStyle = PALETTE.border;
      ctx.lineWidth = 1.5;
      ctx.strokeRect(bx, cy, col.colW, colBoxH);
      ctx.fillStyle = PALETTE.terracotta;
      ctx.font = '700 10px Georgia, serif';
      ctx.fillText(`✦ ${String(col.label ?? '').toUpperCase()} ✦`, bx + 9, cy + 16);
      ctx.fillStyle = PALETTE.ink;
      ctx.font = `400 ${col.valSize}px Georgia, serif`;
      drawWrappedLines(ctx, col.valLines, bx + 9, cy + 30, col.valSize * 1.2);
    });
    cy += columnsBlockH;
  }

  // "Winnie says" quote line — up to 2 lines (see measurement-pass comment
  // above for why this changed from a 1-line cap).
  if (quote) {
    ctx.fillStyle = PALETTE.sage;
    ctx.font = `italic 400 ${quoteSize}px Georgia, serif`;
    drawWrappedLines(ctx, quoteLines, left, cy + quoteSize, quoteLineHeight);
    cy += quoteBlockH;
  }

  ctx.restore(); // lift the clip before drawing the footer in its reserved strip

  // Footer — drawn in the fixed strip reserved at the very bottom of the
  // box (see footerReserve above), never computed from how far `cy` got.
  // This is what actually guarantees it can't collide with the quote line
  // above it, regardless of how long that result's text happens to be.
  ctx.fillStyle = PALETTE.inkSoft;
  ctx.font = '400 12px Georgia, serif';
  ctx.fillText(footerLine || 'Try it yourself at nestandnook.org/tools/', left, box.y + box.height - 6);
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

/**
 * Open a blank browser tab RIGHT NOW, synchronously, inside a click handler
 * — before any `await`. Call this first, then render the canvas, then pass
 * the returned window to `showCanvasInTab`. Doing it in this order (rather
 * than opening the tab after the async render finishes) is what keeps the
 * browser from treating it as an unsolicited popup, since it's still
 * directly inside the user's click gesture.
 * @returns {Window|null}
 */
export function openBlankTab() {
  return window.open('', '_blank');
}

/**
 * Point an already-open tab (from `openBlankTab`) at the canvas as an
 * image. No forced download — the tab just shows the image the way any
 * browser shows an image URL, so the person can view it, right-click to
 * save it, or close the tab, entirely their choice.
 * @param {Window|null} win
 * @param {HTMLCanvasElement} canvas
 */
export function showCanvasInTab(win, canvas) {
  canvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    if (win && !win.closed) {
      win.location.href = url;
    } else {
      // Popup was blocked when we tried to open it ahead of time — try once
      // more now. This may also be blocked since it's no longer inside the
      // original click's gesture window, but it's the best fallback available.
      window.open(url, '_blank');
    }
  }, 'image/png');
}
