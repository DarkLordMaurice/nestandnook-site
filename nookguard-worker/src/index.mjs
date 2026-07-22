// Real Cloudflare Worker entrypoint. Deliberately thin: every real
// decision (routing, validation, the Appendix H invariants, the R2
// content-hash check, Access JWT verification) lives in src/router.mjs /
// src/db.mjs / src/enforce.mjs / src/artifacts.mjs / src/ownerQueue.mjs /
// src/access.mjs, which are plain, dependency-injected functions tested
// directly in tests/ against real SQLite (tests/fakeD1.mjs), a real-enough
// in-memory R2 shim (tests/fakeR2.mjs), and real self-signed RS256 JWTs
// (tests/testJwt.mjs). This file is the only piece of code in this package
// that cannot be unit tested without the actual Workers runtime
// (workerd/Miniflare, via `wrangler dev` or `wrangler deploy`) -- it is a
// few lines of real logic and is not a place further bugs are expected to
// hide. See README.md's "Unresolved risks" for the honest statement of
// what this commit does and does not prove about the real deployed Worker.
import { routeRequest } from './router.mjs';

export default {
  async fetch(request, env) {
    return routeRequest(request, {
      db: env.DB,
      artifacts: env.ARTIFACTS,
      // Both undefined until Maurice provisions a real Access application
      // (see wrangler.toml's ACCESS_AUD/ACCESS_TEAM_DOMAIN placeholders) --
      // access.mjs treats a missing audience as "not provisioned yet,
      // skip verification," matching Commits 14/15's already-documented
      // open-API state rather than breaking every route until then.
      accessAudience: env.ACCESS_AUD,
      jwksFetcher: env.ACCESS_TEAM_DOMAIN
        ? async () => {
          const response = await fetch(`https://${env.ACCESS_TEAM_DOMAIN}/cdn-cgi/access/certs`);
          return response.json();
        }
        : undefined,
    });
  },
};
