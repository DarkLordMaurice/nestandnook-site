// Cloudflare Access JWT verification. When an Access application is
// configured in front of this Worker (or in front of the dashboard that
// calls it), Cloudflare attaches a signed JWT in the `Cf-Access-Jwt-
// Assertion` header on every request that reached the origin -- but the
// Worker itself has no independent way to know Access actually ran unless
// it verifies that JWT itself. This function does real verification: an
// RS256 signature check against the Access team's JWKS, an audience
// check, and an expiry check -- not a stub that always returns true.
//
// Deliberately fails OPEN (`{ ok: true, skipped: true }`) when no
// `audience` is configured, matching Commits 14/15's already-documented
// "No authentication on the Worker API" unresolved risk: this Worker has
// no Access application provisioned yet (needs Maurice's live Cloudflare
// account -- see wrangler.toml's ACCESS_AUD placeholder). Requiring a JWT
// unconditionally before that exists would make every route permanently
// unusable. Once `env.ACCESS_AUD` is set to the real application's AUD
// tag, verification becomes mandatory and fails CLOSED (401) on any
// problem: missing header, malformed token, unknown key ID, bad
// signature, wrong audience, or expiry.

function base64UrlToUint8Array(b64url) {
  const padded = b64url.replace(/-/g, '+').replace(/_/g, '/')
    .padEnd(b64url.length + ((4 - (b64url.length % 4)) % 4), '=');
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function decodeJwtParts(token) {
  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('not a three-part JWT');
  const [headerB64, payloadB64, signatureB64] = parts;
  const header = JSON.parse(new TextDecoder().decode(base64UrlToUint8Array(headerB64)));
  const payload = JSON.parse(new TextDecoder().decode(base64UrlToUint8Array(payloadB64)));
  const signature = base64UrlToUint8Array(signatureB64);
  const signedData = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  return { header, payload, signature, signedData };
}

/**
 * @param request - the incoming Request.
 * @param options.audience - the Access application's AUD tag. If falsy,
 *   verification is skipped entirely (see file comment).
 * @param options.jwksFetcher - () => Promise<{ keys: JWK[] }>, dependency-
 *   injected so tests can supply a real, self-signed test JWKS instead of
 *   Cloudflare's real per-team endpoint
 *   (https://<team>.cloudflareaccess.com/cdn-cgi/access/certs).
 * @param options.now - () => seconds-since-epoch, injected for
 *   deterministic expiry tests.
 */
export async function verifyAccessJwt(request, { audience, jwksFetcher, now = () => Date.now() / 1000 }) {
  if (!audience) {
    return { ok: true, skipped: true };
  }

  const token = request.headers.get('Cf-Access-Jwt-Assertion');
  if (!token) {
    return { ok: false, status: 401, error: 'missing Cf-Access-Jwt-Assertion header' };
  }

  let header;
  let payload;
  let signature;
  let signedData;
  try {
    ({ header, payload, signature, signedData } = decodeJwtParts(token));
  } catch (err) {
    return { ok: false, status: 401, error: `malformed Access JWT: ${String(err && err.message ? err.message : err)}` };
  }

  if (header.alg !== 'RS256') {
    return { ok: false, status: 401, error: `unsupported JWT alg: ${header.alg}` };
  }

  const jwks = await jwksFetcher();
  const jwk = (jwks.keys || []).find((k) => k.kid === header.kid);
  if (!jwk) {
    return { ok: false, status: 401, error: `no matching key for kid ${header.kid}` };
  }

  const cryptoKey = await crypto.subtle.importKey(
    'jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify'],
  );
  const validSignature = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', cryptoKey, signature, signedData);
  if (!validSignature) {
    return { ok: false, status: 401, error: 'invalid JWT signature' };
  }

  const nowSeconds = now();
  if (typeof payload.exp === 'number' && nowSeconds >= payload.exp) {
    return { ok: false, status: 401, error: 'JWT is expired' };
  }
  const audiences = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (!audiences.includes(audience)) {
    return { ok: false, status: 401, error: 'JWT audience does not match this Access application' };
  }

  return { ok: true, email: payload.email, sub: payload.sub };
}
