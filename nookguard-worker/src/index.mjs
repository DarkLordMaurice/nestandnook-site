// Real Cloudflare Worker entrypoint. Deliberately thin: every real
// decision (routing, validation, the two Appendix H invariants) lives in
// src/router.mjs / src/db.mjs / src/enforce.mjs, which are plain,
// dependency-injected functions tested directly in tests/ against real
// SQLite (tests/fakeD1.mjs). This file is the only piece of code in this
// package that cannot be unit tested without the actual Workers runtime
// (workerd/Miniflare, via `wrangler dev` or `wrangler deploy`) -- it is
// two lines of real logic and is not a place further bugs are expected to
// hide. See README.md's "Unresolved risks" for the honest statement of
// what this commit does and does not prove about the real deployed Worker.
import { routeRequest } from './router.mjs';

export default {
  async fetch(request, env) {
    return routeRequest(request, env.DB);
  },
};
