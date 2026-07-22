// Dependency-injected HTTP router: routeRequest(request, db) -> Response.
// This is the entire real logic of the Worker. src/index.mjs (the actual
// `export default { fetch }` Cloudflare entrypoint) is a two-line wrapper
// around this function passing `env.DB` in -- see that file's comment for
// why the split exists. tests/router.test.mjs exercises this function
// directly against tests/fakeD1.mjs's real-SQLite shim, so the request-
// parsing and status-code logic below is under real test coverage even
// though it can never run against the live Workers runtime in this
// sandbox (no wrangler/workerd -- see README.md).

import {
  insertEvent, listEventsByRunId,
  insertGenerationAttempt, getGenerationAttempt,
  insertReview, listReviewsByCandidate,
} from './db.mjs';

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

async function readJsonBody(request) {
  try {
    return { ok: true, body: await request.json() };
  } catch (err) {
    return { ok: false, error: `request body is not valid JSON: ${String(err && err.message ? err.message : err)}` };
  }
}

export async function routeRequest(request, db) {
  const url = new URL(request.url);
  const { pathname } = url;
  const { method } = request;

  if (method === 'POST' && pathname === '/events') {
    const parsed = await readJsonBody(request);
    if (!parsed.ok) return json({ ok: false, error: parsed.error }, 400);
    const result = await insertEvent(db, parsed.body);
    return json(result, result.status);
  }

  if (method === 'GET' && pathname === '/events') {
    const runId = url.searchParams.get('run_id');
    if (!runId) return json({ ok: false, error: 'run_id query parameter is required' }, 400);
    const result = await listEventsByRunId(db, runId);
    return json(result, result.status);
  }

  if (method === 'POST' && pathname === '/generation_attempts') {
    const parsed = await readJsonBody(request);
    if (!parsed.ok) return json({ ok: false, error: parsed.error }, 400);
    const result = await insertGenerationAttempt(db, parsed.body);
    return json(result, result.status);
  }

  const attemptMatch = pathname.match(/^\/generation_attempts\/([^/]+)$/);
  if (method === 'GET' && attemptMatch) {
    const result = await getGenerationAttempt(db, decodeURIComponent(attemptMatch[1]));
    return json(result, result.status);
  }

  if (method === 'POST' && pathname === '/reviews') {
    const parsed = await readJsonBody(request);
    if (!parsed.ok) return json({ ok: false, error: parsed.error }, 400);
    const result = await insertReview(db, parsed.body);
    return json(result, result.status);
  }

  if (method === 'GET' && pathname === '/reviews') {
    const candidateSha256 = url.searchParams.get('candidate_sha256');
    if (!candidateSha256) return json({ ok: false, error: 'candidate_sha256 query parameter is required' }, 400);
    const result = await listReviewsByCandidate(db, candidateSha256);
    return json(result, result.status);
  }

  return json({ ok: false, error: `no route for ${method} ${pathname}` }, 404);
}
