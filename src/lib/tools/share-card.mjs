/**
 * share-card.mjs
 * Shared canvas-based "shareable result card" renderer for Nest & Nook tools.
 * Produces a 1080x1080 downloadable PNG using the site's real brand palette
 * (see src/styles/global.css :root — cream/paper/ink/terracotta/mustard/
 * sage/jewel-teal/gold). No external image assets, no dependencies, no
 * network calls — everything is drawn with the native Canvas 2D API so it
 * works the same offline as it does live.
 *
 * Added 2026-07-16 per Maurice's explicit request that tool results include
 * "something shareable they receive at the end like an info graphic or
 * certificate" — the 2 pre-existing tools (space-and-the-stars,
 * your-small-space-personality) only ever had a "copy result text to
 * clipboard" share action; this is a genuine step up, not a retrofit of
 * that pattern. Reused across all 3 new tools built the same day
 * (why-doesnt-this-feel-done-yet, regret-proof-purchase-check,
 * roast-my-space) so the visual format is consistent no matter which tool
 * produced the card.
 *
 * Pure JS — no imports, no side effects beyond the canvas it's given.
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

/**
 * Draw a shareable result card onto a canvas.
 * @param {HTMLCanvasElement} canvas
 * @param {{ kicker: string, headline: string, body: string, footerLine?: string }} opts
 */
export function renderShareCard(canvas, { kicker, headline, body, footerLine }) {
  const size = 1080;
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // Background + frame
  ctx.fillStyle = PALETTE.cream;
  ctx.fillRect(0, 0, size, size);
  ctx.strokeStyle = PALETTE.border;
  ctx.lineWidth = 3;
  ctx.strokeRect(24, 24, size - 48, size - 48);

  // Top jewel-teal brand band
  const bandHeight = 140;
  ctx.fillStyle = PALETTE.jewelTeal;
  ctx.fillRect(24, 24, size - 48, bandHeight);
  ctx.textBaseline = 'middle';
  ctx.fillStyle = PALETTE.creamOnDark;
  ctx.font = '600 40px Georgia, "Iowan Old Style", serif';
  ctx.fillText('Nest & Nook', 60, 24 + bandHeight / 2 - 12);
  ctx.fillStyle = PALETTE.gold;
  ctx.font = '400 22px Georgia, serif';
  ctx.fillText('nestandnook.org', 60, 24 + bandHeight / 2 + 26);
  ctx.textBaseline = 'alphabetic';

  // Kicker + gold rule
  ctx.fillStyle = PALETTE.terracotta;
  ctx.font = '700 26px Georgia, serif';
  ctx.fillText(String(kicker ?? '').toUpperCase(), 60, bandHeight + 100);
  ctx.strokeStyle = PALETTE.gold;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(60, bandHeight + 122);
  ctx.lineTo(220, bandHeight + 122);
  ctx.stroke();

  // Headline
  ctx.fillStyle = PALETTE.ink;
  ctx.font = '700 60px Georgia, "Iowan Old Style", serif';
  const headlineHeight = wrapText(ctx, headline, 60, bandHeight + 205, size - 120, 68);

  // Body
  ctx.fillStyle = PALETTE.inkSoft;
  ctx.font = '400 30px Arial, "Segoe UI", sans-serif';
  wrapText(ctx, body, 60, bandHeight + 205 + headlineHeight + 55, size - 120, 42);

  // Footer
  ctx.fillStyle = PALETTE.sage;
  ctx.font = 'italic 400 24px Georgia, serif';
  ctx.fillText(footerLine || 'Try it yourself at nestandnook.org/tools/', 60, size - 70);
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
