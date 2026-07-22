// Dependency-injected HTTP router: routeRequest(request, env) -> Response,
// where `env` is `{ db, artifacts, accessAudience, jwksFetcher }` -- a
// D1-shaped ledger database, an R2-shaped artifact bucket (Commit 15), and
// the two optional pieces Commit 16 added for gating the owner-queue
// resolve action behind Cloudflare Access (see src/access.mjs; both are
// undefined by default, which src/access.mjs treats as "not provisioned
// yet, skip verification" -- see that file's own comment). Nothing outside
// this package depends on the env shape yet (the Python side hasn't been
// wired to call this Worker at all), so each commit that's added a new
// binding has updated the shape directly rather than keeping the old one
// around for compatibility. This is the entire real logic of the Worker.
// src/index.mjs (the actual `export default { fetch }` Cloudflare
// entrypoint) is a thin wrapper around this function -- see that file's
// comment for why the split exists. tests/router.test.mjs exercises this
// function directly against tests/fakeD1.mjs, tests/fakeR2.mjs, and real
// RS256 JWTs (tests/testJwt.mjs), so the request-parsing and status-code
// logic below is under real test coverage even though it can never run
// against the live Workers runtime in this sandbox (no wrangler/workerd --
// see README.md).

import {
  insertEvent, listEventsByRunId,
  insertGenerationAttempt, getGenerationAttempt,
  insertReview, listReviewsByCandidate,
} from './db.mjs';
import { putArtifact, getArtifact, headArtifact } from './artifacts.mjs';
import {
  enqueueOwnerDecision, listOwnerDecisions, resolveOwnerDecision,
} from './ownerQueue.mjs';
import { verifyAccessJwt } from './access.mjs';

// Permissive by design for now: this Worker has no Access application of
// its own provisioned yet (see access.mjs's file comment), so there is no
// real "known dashboard origin" to allow-list against today. Once a real
// dashboard origin exists this should narrow to that origin specifically
// -- flagged in README "Unresolved risks", not silently left as `*`
// forever.
const CORS_HEADERS = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET, POST, PUT, HEAD, OPTIONS',
  'access-control-allow-headers': 'content-type, cf-access-jwt-assertion',
};

function withCors(response) {
  for (const [key, value] of Object.entries(CORS_HEADERS)) {
    response.headers.set(key, value);
  }
  return response;
}

function json(body, status) {
  return withCors(new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  }));
}

async function readJsonBody(request) {
  try {
    return { ok: true, body: await request.json() };
  } catch (err) {
    return { ok: false, error: `request body is not valid JSON: ${String(err && err.message ? err.message : err)}` };
  }
}

export async function routeRequest(request, env) {
  const { db, artifacts, accessAudience, jwksFetcher } = env;
  const url = new URL(request.url);
  const { pathname } = url;
  const { method } = request;

  if (method === 'OPTIONS') {
    return withCors(new Response(null, { status: 204 }));
  }

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

  const artifactMatch = pathname.match(/^\/artifacts\/([^/]+)$/);

  if (method === 'PUT' && artifactMatch) {
    const sha256 = decodeURIComponent(artifactMatch[1]);
    let bytes;
    try {
      bytes = await request.arrayBuffer();
    } catch (err) {
      return json({ ok: false, error: `could not read request body: ${String(err && err.message ? err.message : err)}` }, 400);
    }
    const contentType = request.headers.get('content-type') || undefined;
    const result = await putArtifact(artifacts, sha256, bytes, contentType);
    return json(result, result.status);
  }

  if (method === 'GET' && artifactMatch) {
    const sha256 = decodeURIComponent(artifactMatch[1]);
    const result = await getArtifact(artifacts, sha256);
    if (!result.ok) return json(result, result.status);
    const body = await result.object.arrayBuffer();
    const headers = { 'content-length': String(body.byteLength) };
    if (result.object.httpMetadata && result.object.httpMetadata.contentType) {
      headers['content-type'] = result.object.httpMetadata.contentType;
    }
    return withCors(new Response(body, { status: 200, headers }));
  }

  if (method === 'HEAD' && artifactMatch) {
    const sha256 = decodeURIComponent(artifactMatch[1]);
    const result = await headArtifact(artifacts, sha256);
    if (!result.ok) return withCors(new Response(null, { status: result.status }));
    const headers = { 'content-length': String(result.size) };
    if (result.contentType) headers['content-type'] = result.contentType;
    return withCors(new Response(null, { status: 200, headers }));
  }

  if (method === 'POST' && pathname === '/owner_queue') {
    const parsed = await readJsonBody(request);
    if (!parsed.ok) return json({ ok: false, error: parsed.error }, 400);
    const result = await enqueueOwnerDecision(db, parsed.body);
    return json(result, result.status);
  }

  if (method === 'GET' && pathname === '/owner_queue') {
    const status = url.searchParams.get('status') || 'pending';
    const result = await listOwnerDecisions(db, status);
    return json(result, result.status);
  }

  const resolveMatch = pathname.match(/^\/owner_queue\/([^/]+)\/resolve$/);
  if (method === 'POST' && resolveMatch) {
    // The one write action a human actually takes through the dashboard
    // (Appendix J: "Maurice can see and resolve only the owner queue from
    // the private dashboard") -- the only route in this Worker gated
    // behind Access verification. See access.mjs: this is a no-op skip
    // until env.ACCESS_AUD is configured against a real, provisioned
    // Access application.
    const accessResult = await verifyAccessJwt(request, { audience: accessAudience, jwksFetcher });
    if (!accessResult.ok) return json({ ok: false, error: accessResult.error }, accessResult.status);

    const entryId = decodeURIComponent(resolveMatch[1]);
    const parsed = await readJsonBody(request);
    if (!parsed.ok) return json({ ok: false, error: parsed.error }, 400);

    // When Access is actually configured and verified (not skipped), the
    // resolver's identity is whatever the verified JWT says -- never a
    // client-supplied resolved_by, which would otherwise let anyone who
    // can reach this route claim to be Maurice. Only when Access is
    // un-provisioned (accessResult.skipped) is there no verified identity
    // to fall back on, so a client-supplied resolved_by is trusted, same
    // as every other currently-unauthenticated route in this Worker.
    const resolvedBy = accessResult.skipped ? parsed.body.resolved_by : accessResult.email;
    const result = await resolveOwnerDecision(db, { ...parsed.body, entry_id: entryId, resolved_by: resolvedBy });
    return json(result, result.status);
  }

  return json({ ok: false, error: `no route for ${method} ${pathname}` }, 404);
}
