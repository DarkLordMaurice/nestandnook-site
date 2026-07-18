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
  // Never truncate with an ellipsis (Maurice, 2026-07-18: "never lose
  // content, shrink everything else instead"). At minSize, return every
  // wrapped line uncapped rather than slicing to maxLines — the caller's
  // layout may run long on a worst-case result, but nothing is ever cut.
  //
  // FIXED 2026-07-18: the previous version here truncated to maxLines and
  // appended "…", shrinking the last line one character at a time until it
  // fit. That loop compared against `last`, a copy of the line captured
  // ONCE before the loop started — but the loop body only ever shrank
  // `lines[maxLines - 1]`, never `last` itself. So the while condition
  // re-tested the exact same (never-shrinking) string on every pass. For
  // any text whose original last line was too wide to ever fit even at 1
  // character (true worst-case content — e.g. space-and-the-stars' Taurus
  // profile, its longest field on the site's shortest content box), this
  // was a genuine infinite loop that pinned the render thread forever —
  // the real cause of the "site keeps crashing, can't load tools" report,
  // confirmed by reproducing the hang live on Taurus specifically and
  // ruling out every shorter sign.
  ctx.font = `${weightFamily} ${minSize}px Georgia, "Iowan Old Style", serif`;
  const lines = measureWrappedLines(ctx, text, maxWidth);
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

  // REBUILT 2026-07-18 (6th pass): the cream translucent PANEL from the
  // previous pass is GONE. Maurice, explicit and unambiguous, pointing at
  // his own reference Scorpio card: "There shouldnt be fucking cream panel
  // at fucking all... the text should have a transparent fucking background
  // so it can sit on fucking anything." The reference card has no separate
  // bordered/filled card UI sitting on top of the frame — text sits directly
  // on the frame's own cream parchment texture, filling almost the entire
  // measured blank rectangle. `panelX/Y/W/H` below are now just an invisible
  // LAYOUT box (still inset slightly off the frame's own decorative corner
  // medallions so text can't collide with them) — nothing is drawn for it.
  const panelInsetX = Math.max(6, box.width * 0.015);
  const panelTopInset = Math.max(6, box.height * 0.02);
  const panelBottomInset = Math.max(4, box.height * 0.015);
  const panelX = box.x + panelInsetX;
  const panelY = box.y + panelTopInset;
  const panelW = box.width - panelInsetX * 2;
  const panelH = box.height - panelTopInset - panelBottomInset;

  const centerX = panelX + panelW / 2;
  // Text now runs close to edge-to-edge within the panel (0.94), matching
  // the reference card's proportions, rather than the old narrow 0.8
  // column floating with dead margin on either side — the panel itself
  // already guarantees contrast against whatever art sits underneath, so
  // there's no longer a reason to additionally shrink away from it.
  const contentWidth = panelW * 0.94;
  const left = centerX - contentWidth / 2;

  // Roomy vs. tight bucket, decided here (right after panelH/panelW are
  // known) so topReserve/footerReserve below can be bucket-aware too, not
  // just the font/line-budget constants further down.
  //
  // FIXED 2026-07-18 (3rd bug in this same rebuild, caught live on
  // your-small-space-personality's "Nester" result — the "Winnie says"
  // quote was silently missing entirely, not just cramped): this was
  // height-only (`panelH >= 320`), which correctly isolated
  // space-and-the-stars (≈302px tall, the shortest) into the tight bucket
  // — but your-small-space-personality's panel is tall ENOUGH (≈342px) to
  // read as roomy while also being the NARROWEST panel of all 5 (≈549px
  // wide, vs. 600-850px for the other 4). A narrow width forces body text
  // to wrap into more lines at any given font size regardless of how much
  // vertical room exists, so the "roomy" bucket's bigger font/looser line
  // caps produced a body block tall enough that, combined with the
  // headline/badge/columns above it, pushed the quote section entirely
  // past the clip — invisible, the same failure mode as the 2nd bug above,
  // just triggered by width instead of height this time. A panel now has
  // to be both tall AND wide enough to count as roomy; measured real
  // panelW: space-and-the-stars ≈765px, your-small-space-personality
  // ≈549px, regret-proof-purchase-check ≈602px, roast-my-space ≈737px,
  // why-doesnt-this-feel-done-yet ≈849px. 650 sits strictly between the
  // narrow pair (549, 602) and the wide pair (737, 849).
  const isRoomyBox = panelH >= 320 && panelW >= 650;

  // Extra top clearance inside the panel, clear of the ornamental corner
  // medallions that cut diagonally into the frame's blank rectangle
  // (flagged 2026-07-18 on roast-my-space — "text gets clipped by the
  // actual border"). Smaller on the tight bucket — every pixel here is a
  // pixel not available to the column boxes and quote below it.
  const topReserve = isRoomyBox ? Math.max(10, panelH * 0.04) : Math.max(3, panelH * 0.01);

  // Hard clip to the panel. Everything below is a best-effort layout that
  // tries to fit within it, but fitFontSize no longer truncates content
  // (see its own comment above) — if a worst-case result still runs a
  // touch long, this clip is just the last-resort guarantee it can't
  // bleed onto the frame's own border artwork, not a content-loss
  // mechanism. A reserved footer strip is carved out first and drawn in
  // its own un-clipped pass at a fixed position, so the two can never
  // overlap regardless of how long the content above happens to run.
  const footerReserve = isRoomyBox ? 22 : 19;
  const availableHeight = panelH - footerReserve - topReserve;

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

  // Every size/line-budget constant below is bucket-aware (roomy vs. tight)
  // rather than a single global value, calibrated against the ACTUAL
  // longest copy in each tool's dataset (measured directly via a one-off
  // script against every tool's .mjs data file — not guessed, and not
  // spot-checked against whichever example happened to get clicked during
  // testing). Worst case measured 2026-07-18: space-and-the-stars' Taurus
  // profile, 423 chars — the longest body copy on the site — on its own
  // 313px-tall frame, the shortest of the 5.
  //
  // FIXED 2026-07-18 (same day, twice, both caught via real live
  // screenshots after shipping the panel — text estimates from a formula
  // are not a substitute for actually looking at the render):
  // 1st bug: the roomy/tight threshold was `panelH >= 300`, based on a
  // guessed panel height. The real computed panel heights are
  // space-and-the-stars ≈302px (the tightest), your-small-space-
  // personality ≈342px, regret-proof-purchase-check ≈360px, roast-my-space
  // ≈397px, why-doesnt-this-feel-done-yet ≈483px — so a >=300 cutoff put
  // EVERY tool, including the tightest, in the roomier bucket. 320 sits
  // strictly between the real tightest (302) and next-tightest (342), so
  // space-and-the-stars is now the only tool in the tighter bucket.
  // 2nd bug: even after fixing the threshold, only body's line budget was
  // bucket-aware — glyph size, headline font, and badge height were still
  // one fixed value for every box. The glyph alone (46px) was forcing the
  // headline row to at least 52px tall regardless of font size, and a
  // 4-line body at a near-max font still ran the total content height well
  // past the tight panel's available space, pushing the column boxes and
  // the "Winnie says" quote entirely past the bottom of the clip —
  // invisible, not just cramped. Every size constant below now has its own
  // tight-bucket value, not just body's line cap.

  // FIXED 2026-07-18 (6th pass): every ceiling below was raised substantially.
  // Maurice's reference card uses large, space-filling text — the panel used
  // to hide how conservative these ceilings were, since a bunch of dead
  // panel-colored space around smaller text still looked "finished." With
  // the panel gone, undersized text reads as literal empty background
  // showing through, which is exactly the complaint ("the text should be in
  // the center of this image covering almost its entirety"). fitFontSize
  // still auto-shrinks per-result (e.g. Taurus's 423-char worst-case body vs.
  // Gemini's one-line kryptonite), so raising the ceiling only affects
  // results that have room to be bigger — it doesn't remove the safety floor
  // that prevents overflow on long content.
  // CORRECTED same pass: the tight bucket (space-and-the-stars only, 302px
  // panel) overflowed on Taurus (worst-case body) when raised as far as the
  // roomy bucket — "Winnie says" and the quote got clipped off entirely.
  // Tight bucket now gets a smaller, safer bump than roomy, not the same
  // ceiling.
  const eyebrowCore = kicker ? (isRoomyBox ? 20 : 15) : 0;

  const glyphSize = isRoomyBox ? 58 : 38;
  // The headline gets a WIDER allowance than the content column (panelW *
  // 0.96 vs. the 0.94 used for body/columns/quote below) — headlines are
  // short (1-3 words) and should almost never need to wrap, so they get
  // nearly the panel's full width instead.
  const headlineFullWidth = panelW * 0.96;
  let headlineX = left;
  let headlineMaxWidth = headlineFullWidth;
  if (glyph) {
    headlineX = left + glyphSize + 14;
    headlineMaxWidth = headlineFullWidth - glyphSize - 14;
  }
  const headlineText = String(headline ?? '');
  const { size: headlineSize, lines: headlineLines } = isRoomyBox
    ? fitFontSize(ctx, headlineText, '700', headlineMaxWidth, 2, 64, 28)
    : fitFontSize(ctx, headlineText, '700', headlineMaxWidth, 2, 38, 24);
  const headlineLineHeight = headlineSize * 1.12;
  const headlineCore = Math.max(headlineLineHeight * headlineLines.length, glyphSize + 6);

  let pillW = 0;
  const pillH = isRoomyBox ? 30 : 22;
  const badgeLabel = badge ? String(badge).toUpperCase() : '';
  const badgeFontSize = isRoomyBox ? 16 : 13;
  if (badge) {
    ctx.font = `700 ${badgeFontSize}px Georgia, serif`;
    pillW = ctx.measureText(badgeLabel).width + 34;
    // Badge can now hold a long archetype name (e.g. "The All-or-Nothing
    // Reorganizer", 30 chars) rather than always a short word — cap its
    // width so a long badge can't overflow past the content column.
    pillW = Math.min(pillW, contentWidth);
  }
  const badgeCore = badge ? pillH : 0;

  const bodyMaxLines = isRoomyBox ? 5 : 4;
  const columnMaxLines = isRoomyBox ? 4 : 3;

  let bodySize = 0;
  let bodyLines = [];
  if (body) {
    const r = isRoomyBox
      ? fitFontSize(ctx, body, '400', contentWidth, bodyMaxLines, 22, 13)
      : fitFontSize(ctx, body, '400', contentWidth, bodyMaxLines, 12, 11);
    bodySize = r.size;
    bodyLines = r.lines;
  }
  const bodyLineHeight = bodySize * 1.4;
  const bodyCore = body ? bodyLineHeight * bodyLines.length : 0;

  const colGap = 18;
  const colPadX = 16;
  const hasColumns = Boolean(columns && columns.length);
  const starCore = hasColumns ? (isRoomyBox ? 16 : 11) : 0;
  const colLineH = isRoomyBox ? 21 : 15;
  const colsData = [];
  if (hasColumns) {
    const colW = (contentWidth - colGap * (columns.length - 1)) / columns.length;
    columns.forEach((col) => {
      const r = isRoomyBox
        ? fitFontSize(ctx, col.value ?? '', '400', colW - colPadX * 2, columnMaxLines, 17, 11)
        : fitFontSize(ctx, col.value ?? '', '400', colW - colPadX * 2, columnMaxLines, 12, 9);
      colsData.push({ label: col.label, colW, valSize: r.size, valLines: r.lines });
    });
  }
  // Box height grows with whatever the longest column actually needs
  // instead of a flat constant — a fixed-height box truncated "What to
  // watch for" copy with an ellipsis once the narrower content column
  // pushed that column's text to wrap further than expected.
  const maxValLines = hasColumns ? Math.max(1, ...colsData.map((c) => c.valLines.length)) : 0;
  const colBoxH = hasColumns ? (isRoomyBox ? 24 : 18) + maxValLines * colLineH + 8 : 0;
  const columnsCore = hasColumns ? colBoxH : 0;

  // "Winnie says" heading (own line, matches the reference card's
  // "✦ Winnie says ✦" label) + the quote text itself below it, plain (no
  // literal quotation marks — the reference doesn't quote-mark it either).
  // maxLines bumped 2→3: your-small-space-personality's longest quote
  // (203 chars) on its narrower 566px-wide frame needs the extra line at
  // a legible size.
  const winnieLabelCore = quote ? (isRoomyBox ? 16 : 14) : 0;
  let quoteSize = 0;
  let quoteLines = [];
  if (quote) {
    const r = isRoomyBox
      ? fitFontSize(ctx, quote, '400', contentWidth, 4, 19, 12)
      : fitFontSize(ctx, quote, '400', contentWidth, 3, 14, 10);
    quoteSize = r.size;
    quoteLines = r.lines;
  }
  const quoteLineHeight = quoteSize * (isRoomyBox ? 1.3 : 1.25);
  const quoteCore = quote ? quoteLineHeight * quoteLines.length : 0;

  // Gaps are the ONLY thing allowed to compress under pressure — text
  // itself already shrinks to its own floor via fitFontSize above. Every
  // gap below scales down together, proportionally, whenever the nominal
  // total doesn't fit — see the scale-factor block right after this.
  const gaps = isRoomyBox
    ? {
        eyebrow: kicker ? 12 : 0,
        headline: 13,
        badge: badge ? 12 : 0,
        body: body ? 13 : 0,
        star: hasColumns ? 8 : 0,
        columns: hasColumns ? 13 : 0,
        winnieLabel: quote ? 6 : 0,
      }
    : {
        eyebrow: kicker ? 8 : 0,
        headline: 9,
        badge: badge ? 8 : 0,
        body: body ? 9 : 0,
        star: hasColumns ? 5 : 0,
        columns: hasColumns ? 9 : 0,
        winnieLabel: quote ? 4 : 0,
      };
  const totalCore = eyebrowCore + headlineCore + badgeCore + bodyCore + starCore + columnsCore + winnieLabelCore + quoteCore;
  const totalGapsNominal = Object.values(gaps).reduce((a, b) => a + b, 0);
  const nominalTotalH = totalCore + totalGapsNominal;
  if (nominalTotalH > availableHeight) {
    const excess = nominalTotalH - availableHeight;
    const minGapEach = isRoomyBox ? 2 : 1;
    const activeGapCount = Object.values(gaps).filter((g) => g > 0).length;
    const maxReducible = Math.max(0, totalGapsNominal - activeGapCount * minGapEach);
    const reduction = Math.min(excess, maxReducible);
    const scale = totalGapsNominal > 0 ? (totalGapsNominal - reduction) / totalGapsNominal : 1;
    Object.keys(gaps).forEach((k) => {
      gaps[k] = gaps[k] > 0 ? Math.max(minGapEach, gaps[k] * scale) : 0;
    });
  } else if (nominalTotalH < availableHeight && totalGapsNominal > 0) {
    // FIXED 2026-07-18 (4th bug — flagged directly by Maurice via a
    // screenshot with the empty regions circled in red): shorter results
    // (e.g. Gemini's short "Finishing." kryptonite vs. Taurus's long
    // worst-case text) leave real leftover room inside the panel, but that
    // leftover was previously dumped entirely into ONE lump — half above
    // the eyebrow, half below the quote — via `slack` below. The panel is
    // sized to the frame's full measured blank rectangle on purpose (so
    // borders don't need to shrink), which means the leftover room is real
    // and expected; the bug was concentrating it at the two outer edges
    // instead of spreading it between sections, which read as two big dead
    // margins with everything else still cramped together in the middle —
    // exactly what doesn't match the reference card's evenly-filled look.
    // Fix: absorb most of the slack into the gaps themselves (proportional
    // scale-up, mirroring the scale-DOWN branch above), capped at 2.4x so
    // very short results (e.g. a one-word kryptonite) don't produce
    // absurdly large gaps — the remainder still centers as edge margin via
    // `slack` below, but it's now a small remainder, not the whole budget.
    // Tight bucket gets a lower cap than roomy: on a 296px panel, scaling
    // gaps all the way up to 2.4x pushed the quote's last line right up
    // against the clip edge with almost no breathing room before the fixed
    // footer strip, so the two visually collided on long results like
    // Taurus even though nothing was technically clipped. A lower cap
    // leaves more of the slack as plain top/bottom margin (via `slack`
    // below) instead of packing it all between sections.
    const room = availableHeight - nominalTotalH;
    const maxScale = isRoomyBox ? 2.4 : 1.3;
    const rawScale = 1 + (room * 0.75) / totalGapsNominal;
    const scale = Math.min(maxScale, rawScale);
    Object.keys(gaps).forEach((k) => {
      gaps[k] = gaps[k] > 0 ? gaps[k] * scale : 0;
    });
  }
  const totalGaps = Object.values(gaps).reduce((a, b) => a + b, 0);
  if (typeof window !== 'undefined' && window.__nnDebugCert) {
    console.log('NN_DEBUG', JSON.stringify({ isRoomyBox, panelH, panelW, topReserve, footerReserve, availableHeight, totalCore, totalGapsNominal, nominalTotalH, totalGaps, bodySize, bodyLines: bodyLines.length, quoteSize, quoteLines: quoteLines.length, colBoxH, headlineSize, headlineCore, eyebrowCore, badgeCore, bodyCore, starCore, columnsCore, winnieLabelCore, quoteCore }));
  }

  const eyebrowH = eyebrowCore + gaps.eyebrow;
  const headlineBlockH = headlineCore + gaps.headline;
  const badgeBlockH = badgeCore + gaps.badge;
  const bodyBlockH = bodyCore + gaps.body;
  const starH = starCore + gaps.star;
  const columnsBlockH = columnsCore + gaps.columns;
  const winnieLabelH = winnieLabelCore + gaps.winnieLabel;

  const totalContentH = totalCore + totalGaps;
  const slack = Math.max(0, availableHeight - totalContentH);
  // Only ever pushes content DOWN from the panel's top edge to center it in
  // extra room — never up, and never past what clip already guards against.
  const startY = panelY + topReserve + slack / 2;

  ctx.save();
  ctx.beginPath();
  ctx.rect(panelX, panelY + topReserve, panelW, panelH - footerReserve - topReserve);
  ctx.clip();

  let cy = startY;

  // Everything below is center-aligned as a unit, matching the reference
  // certificate Maurice provided — the first version of this rebuild only
  // matched the reference's section LIST (eyebrow/headline/badge/body/
  // columns/quote), not its actual look: that reference is fully centered,
  // uses a dark-green headline with gold accents (not near-black ink with
  // terracotta accents), and has a "✦ Winnie says ✦" label line above the
  // quote plus a small star flourish above the column boxes — none of which
  // the first pass had. Fixed 2026-07-18 (second correction, same day).

  // Eyebrow line
  if (kicker) {
    ctx.fillStyle = PALETTE.gold;
    ctx.font = '700 17px Georgia, serif';
    ctx.textAlign = 'center';
    ctx.fillText(String(kicker).toUpperCase(), centerX, cy + 14);
    cy += eyebrowH;
  }

  // Headline, with an optional glyph to its left — centered as one unit.
  // Multi-line headlines only center-align the glyph against the FIRST
  // line; subsequent lines are centered independently, which is an
  // acceptable simplification since every result name so far is 1-2 words
  // and fits on one line at the chosen size.
  {
    const firstLineWidth = (() => {
      ctx.font = `700 ${headlineSize}px Georgia, "Iowan Old Style", serif`;
      return ctx.measureText(headlineLines[0] || '').width;
    })();
    const unitWidth = glyph ? glyphSize + 14 + firstLineWidth : firstLineWidth;
    const unitStartX = centerX - unitWidth / 2;
    if (glyph) {
      drawGlyphIcon(ctx, glyph.type, unitStartX + glyphSize / 2, cy + 22, glyphSize, PALETTE.gold);
      if (glyph.type === 'text' && glyph.value) {
        ctx.fillStyle = PALETTE.gold;
        ctx.font = `700 ${glyphSize}px Georgia, serif`;
        ctx.textAlign = 'left';
        // U+FE0E (text presentation selector, written as an explicit JS
        // escape below so there's no ambiguity about which invisible
        // codepoint actually landed in the file) forces the plain serif
        // glyph instead of a colored emoji-style icon. Without it, Windows
        // falls back to Segoe UI Emoji/Symbol for zodiac characters like
        // "♏" — rendering a small colored badge instead of elegant text,
        // flagged 2026-07-18 as looking like "a cheap text icon."
        // Built via String.fromCharCode rather than a literal embedded
        // character — a literal U+FE0E typed through the editor round-trip
        // actually landed as U+FE0F (confirmed via a raw byte dump: EF B8 8F,
        // the UTF-8 encoding of FE0F) — the EMOJI selector, the exact
        // opposite of what's needed here. fromCharCode(0xFE0E) is
        // unambiguous regardless of editor/encoding behavior.
        const textPresentationGlyph = `${glyph.value}${String.fromCharCode(0xfe0e)}`;
        ctx.fillText(textPresentationGlyph, unitStartX, cy + 38);
      }
    }
    ctx.fillStyle = PALETTE.jewelTeal;
    ctx.font = `700 ${headlineSize}px Georgia, "Iowan Old Style", serif`;
    ctx.textAlign = 'left';
    ctx.fillText(headlineLines[0] || '', glyph ? unitStartX + glyphSize + 14 : unitStartX, cy + headlineSize * 0.78);
    if (headlineLines.length > 1) {
      ctx.textAlign = 'center';
      for (let i = 1; i < headlineLines.length; i += 1) {
        ctx.fillText(headlineLines[i], centerX, cy + headlineSize * 0.78 + i * headlineLineHeight);
      }
    }
  }
  cy += headlineBlockH;

  // Pill subtitle badge — centered
  if (badge) {
    const pillX = centerX - pillW / 2;
    ctx.fillStyle = PALETTE.jewelTeal;
    ctx.beginPath();
    ctx.roundRect(pillX, cy, pillW, pillH, pillH / 2);
    ctx.fill();
    ctx.fillStyle = PALETTE.creamOnDark;
    ctx.font = `700 ${badgeFontSize}px Georgia, serif`;
    ctx.textAlign = 'center';
    ctx.fillText(badgeLabel, centerX, cy + pillH / 2 + badgeFontSize * 0.35);
    cy += badgeBlockH;
  }

  // Body paragraph — centered
  if (body) {
    ctx.fillStyle = PALETTE.inkSoft;
    ctx.font = `400 ${bodySize}px Georgia, serif`;
    drawWrappedLines(ctx, bodyLines, centerX, cy + bodySize, bodyLineHeight, 'center');
    cy += bodyBlockH;
  }

  // Small star flourish above the column callout, matching the reference
  if (colsData.length) {
    ctx.fillStyle = PALETTE.gold;
    ctx.font = '400 14px Georgia, serif';
    ctx.textAlign = 'center';
    ctx.fillText('✦', centerX, cy + 14);
    cy += starH;
  }

  // Two-column (or one-column) boxed callout — row centered as a whole,
  // label/value centered within each box
  if (colsData.length) {
    const rowWidth = colsData.reduce((w, c) => w + c.colW, 0) + colGap * (colsData.length - 1);
    const rowStartX = centerX - rowWidth / 2;
    let bx = rowStartX;
    colsData.forEach((col) => {
      const colCenterX = bx + col.colW / 2;
      ctx.strokeStyle = PALETTE.border;
      ctx.lineWidth = 1.5;
      ctx.strokeRect(bx, cy, col.colW, colBoxH);
      ctx.fillStyle = PALETTE.gold;
      ctx.font = '700 10px Georgia, serif';
      ctx.textAlign = 'center';
      ctx.fillText(`✦ ${String(col.label ?? '').toUpperCase()} ✦`, colCenterX, cy + 19);
      ctx.fillStyle = PALETTE.ink;
      ctx.font = `400 ${col.valSize}px Georgia, serif`;
      drawWrappedLines(ctx, col.valLines, colCenterX, cy + 38, col.valSize * 1.2, 'center');
      bx += col.colW + colGap;
    });
    cy += columnsBlockH;
  }

  // "✦ Winnie says ✦" label + the quote itself below it, both centered,
  // no literal quotation marks (matches the reference card).
  if (quote) {
    ctx.fillStyle = PALETTE.gold;
    ctx.font = '700 12px Georgia, serif';
    ctx.textAlign = 'center';
    ctx.fillText('✦ Winnie says ✦', centerX, cy + 13);
    cy += winnieLabelH;
    ctx.fillStyle = PALETTE.inkSoft;
    ctx.font = `400 ${quoteSize}px Georgia, serif`;
    drawWrappedLines(ctx, quoteLines, centerX, cy + quoteSize, quoteLineHeight, 'center');
    cy += quoteLineHeight * quoteLines.length + 6;
  }

  ctx.restore(); // lift the clip before drawing the footer in its reserved strip

  // Footer — drawn in the fixed strip reserved at the very bottom of the
  // panel (see footerReserve above), never computed from how far `cy` got.
  // This is what actually guarantees it can't collide with the quote line
  // above it, regardless of how long that result's text happens to be.
  ctx.fillStyle = PALETTE.inkSoft;
  ctx.font = `400 ${isRoomyBox ? 12 : 10}px Georgia, serif`;
  ctx.textAlign = 'center';
  ctx.fillText(footerLine || 'Try it yourself at nestandnook.org/tools/', centerX, panelY + panelH - (isRoomyBox ? 8 : 6));
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
