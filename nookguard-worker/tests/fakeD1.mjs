// A D1Database-shaped wrapper around Node's built-in node:sqlite, for tests
// only. This is NOT a mock of NookGuard's own logic -- src/db.mjs and
// src/router.mjs run completely unmodified against this object, exactly as
// they would run against the real `env.DB` binding in production. What's
// faked is Cloudflare's D1 *transport* (HTTP-to-the-edge-database), not any
// SQL semantics: node:sqlite is a real SQLite engine, D1 is also SQLite
// under the hood, and this file runs the exact same migration file
// (migrations/0001_init.sql) that a real `wrangler d1 migrations apply`
// would run against a real D1 database.
//
// Real D1's own methods (prepare/bind/run/all/first) are asynchronous
// (they cross a network boundary in production). This shim returns
// Promises from every method for that reason -- so that application code
// written with `await` behaves identically against the fake and the real
// binding, and no application code has to know or care which one it's
// talking to.
//
// Documented, honest limitation (see README.md "Unresolved risks" and the
// Commit 14 BUILD-LOG entry): this proves the schema and the application
// logic are correct against real SQLite. It does NOT exercise Cloudflare's
// actual D1 service, its real network/latency/consistency behavior, or the
// Workers runtime itself (no workerd, no Miniflare) -- those require a
// live or emulated Cloudflare account, which this sandbox does not have.

import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MIGRATION_PATH = path.join(__dirname, '..', 'migrations', '0001_init.sql');

class FakeD1PreparedStatement {
  constructor(db, sql) {
    this._db = db;
    this._sql = sql;
    this._args = [];
  }

  bind(...args) {
    const next = new FakeD1PreparedStatement(this._db, this._sql);
    next._args = args;
    return next;
  }

  async run() {
    try {
      const stmt = this._db.prepare(this._sql);
      const info = stmt.run(...this._args);
      return {
        success: true,
        meta: { changes: info.changes, last_row_id: info.lastInsertRowid },
        results: [],
      };
    } catch (err) {
      return { success: false, error: String(err && err.message ? err.message : err) };
    }
  }

  async all() {
    const stmt = this._db.prepare(this._sql);
    const results = stmt.all(...this._args);
    return { success: true, results, meta: { changes: 0 } };
  }

  async first(column) {
    const stmt = this._db.prepare(this._sql);
    const row = stmt.get(...this._args);
    if (row === undefined) return null;
    if (column) return row[column] ?? null;
    return row;
  }
}

export class FakeD1Database {
  constructor() {
    this._sqlite = new DatabaseSync(':memory:');
  }

  prepare(sql) {
    return new FakeD1PreparedStatement(this._sqlite, sql);
  }

  async exec(sql) {
    this._sqlite.exec(sql);
    return { count: 0, duration: 0 };
  }
}

/** Creates a fresh in-memory FakeD1Database with 0001_init.sql already applied. */
export function createMigratedFakeD1() {
  const db = new FakeD1Database();
  const migrationSql = readFileSync(MIGRATION_PATH, 'utf-8');
  db._sqlite.exec(migrationSql);
  return db;
}
