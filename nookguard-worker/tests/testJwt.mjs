// Real RS256 JWT minting for tests, used only to exercise src/access.mjs.
// Uses Web Crypto (crypto.subtle.generateKey/sign), the same API
// src/access.mjs itself uses to verify -- so these tests prove real
// cryptographic round-tripping, not a stubbed pass-through. What this does
// NOT prove: that Cloudflare's real Access service issues tokens in
// exactly this shape, or that a real Access-issued JWT verifies
// successfully against this code (that needs a live Access application --
// see README "Unresolved risks"). This mints a *structurally identical*
// token (same three-part RS256 JWT shape, same claim names) signed by a
// key generated here instead of by Cloudflare.

function base64UrlFromUint8Array(bytes) {
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlFromJson(obj) {
  return base64UrlFromUint8Array(new TextEncoder().encode(JSON.stringify(obj)));
}

/** Generates a real RSA keypair and returns { publicJwk, privateKey, kid }. */
export async function generateTestKeypair(kid = 'test-key-1') {
  const { publicKey, privateKey } = await crypto.subtle.generateKey(
    { name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' },
    true,
    ['sign', 'verify'],
  );
  const publicJwk = await crypto.subtle.exportKey('jwk', publicKey);
  publicJwk.kid = kid;
  publicJwk.alg = 'RS256';
  publicJwk.use = 'sig';
  return { publicJwk, privateKey, kid };
}

/** Signs a real RS256 JWT with `privateKey`, header kid = `kid`. */
export async function signTestJwt(privateKey, kid, payload) {
  const header = { alg: 'RS256', typ: 'JWT', kid };
  const headerB64 = base64UrlFromJson(header);
  const payloadB64 = base64UrlFromJson(payload);
  const signedData = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const signatureBuffer = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', privateKey, signedData);
  const signatureB64 = base64UrlFromUint8Array(new Uint8Array(signatureBuffer));
  return `${headerB64}.${payloadB64}.${signatureB64}`;
}

/** A jwksFetcher (matching src/access.mjs's expected shape) that always
 * returns the given public JWK(s). */
export function fakeJwksFetcher(...publicJwks) {
  return async () => ({ keys: publicJwks });
}
