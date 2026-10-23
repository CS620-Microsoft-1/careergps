/** Optional real PostgreSQL checks using an in-memory PGlite engine.
 *
 * Usage (from any directory; Python needs the backend requirements):
 *   node backend/tests/check_job_posting_analysis_postgres.mjs /path/to/python \
 *     /path/to/node_modules/@electric-sql/pglite
 *
 * The package is supplied externally; no project dependency is installed. The
 * Python subprocess renders the CURRENT migration files offline, bypassing
 * migrations/env.py and application settings. No .env, database URL, Azure,
 * network socket, Supabase credentials, or real source data is used. PGlite is
 * embedded PostgreSQL, not a test of hosted Supabase configuration or roles.
 */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const [python, packageDirectory] = process.argv.slice(2);
if (!python || !packageDirectory || process.argv.length !== 4) {
  throw new Error('Usage: node check_job_posting_analysis_postgres.mjs PYTHON PGLITE_PACKAGE_DIRECTORY');
}
const backend = fileURLToPath(new URL('..', import.meta.url));
const { PGlite } = await import(pathToFileURL(resolve(packageDirectory, 'dist/index.js')).href);
const render = String.raw`
import io, json
from unittest.mock import patch
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

scripts = ScriptDirectory.from_config(Config('alembic.ini'))
target = scripts.get_revision('7d2c91a4e8b6')
chain = list(reversed(list(scripts.walk_revisions(base='base', head=target.revision))))
def render(revisions, direction):
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name='postgresql', opts={
        'as_sql': True, 'output_buffer': output, 'literal_binds': True,
    })
    with patch('sqlalchemy.create_engine', side_effect=AssertionError('No external database')):
        for revision in revisions:
            with patch.object(revision.module, 'op', Operations(context)):
                getattr(revision.module, direction)()
    return output.getvalue()
print(json.dumps({
    'upgrade': render(chain, 'upgrade'),
    'downgrade': render([target], 'downgrade'),
    'upgrade_only': render([target], 'upgrade'),
}))
`;
const sql = JSON.parse(execFileSync(python, ['-c', render], { cwd: backend, encoding: 'utf8' }));
const db = new PGlite();
const children = ['job_analysis_locations', 'job_analysis_responsibilities',
  'job_analysis_qualifications', 'job_analysis_conditions', 'job_analysis_compensation'];
const tables = ['job_postings_analyses', ...children];
const job = '10000000-0000-4000-8000-000000000001';
const missing = '10000000-0000-4000-8000-000000000002';
const evidence = [{ source_field: 'description_text', quote: 'Python or Go.' }];
const analyzedAt = '2026-10-22T12:34:56.000Z';
let passed = 0;

function insert(table, row) {
  const columns = Object.keys(row);
  return db.query('INSERT INTO ' + table + ' (' + columns.join(',') + ') VALUES (' +
    columns.map((_, i) => '$' + (i + 1)).join(',') + ') RETURNING *', Object.values(row));
}
function parent(overrides = {}) {
  return insert('job_postings_analyses', {
    job_posting_id: job, job_family: 'ai_engineer', seniority: 'intern',
    source_content_hash: 'synthetic-v1', agent_version: '13', analyzed_at: analyzedAt, ...overrides,
  });
}
function child(table, overrides = {}) {
  return insert(table, { job_posting_id: job, position: 0, value: 'Python or Go.',
    evidence: JSON.stringify(evidence),
    ...(table === 'job_analysis_qualifications' ? { level: 'required', categories: ['skill', 'experience'] } : {}),
    ...(table === 'job_analysis_conditions' ? { type: 'visa_sponsorship' } : {}),
    ...(table === 'job_analysis_compensation' ? { type: 'base_salary', minimum: '123456.123456789' } : {}),
    ...overrides,
  });
}
async function reject(fn, code = '23514') {
  await db.exec('SAVEPOINT expected_failure');
  let error;
  try { await fn(); } catch (failure) { error = failure; }
  await db.exec('ROLLBACK TO SAVEPOINT expected_failure; RELEASE SAVEPOINT expected_failure');
  assert.ok(error, 'Expected database rejection');
  assert.equal(error.code, code, error.message);
}
async function test(name, fn) {
  await db.exec('BEGIN');
  try { await fn(); passed++; console.log('PASS', name); }
  finally { await db.exec('ROLLBACK'); }
}

try {
  // Synthetic prerequisite for the existing resume migration, not a Supabase connection.
  await db.exec('CREATE SCHEMA auth; CREATE TABLE auth.users (id uuid PRIMARY KEY)');
  await db.exec(sql.upgrade);
  console.log('PASS full migration chain:', (await db.query('SELECT version()')).rows[0].version);
  passed++;
  await db.query('INSERT INTO job_postings ' +
    '(id,source,external_id,company_slug,company_name,company_tier,title,description_text,url,' +
    'first_seen_at,last_seen_at,content_hash) VALUES ' +
    "($1,'greenhouse','example-1','example','Example','other','AI Engineer Intern'," +
    "'Python or Go.','https://example.test/job',now(),now(),'synthetic-v1')", [job]);
  await db.exec('CREATE ROLE jpa_check_reader NOLOGIN; ' +
    'GRANT USAGE ON SCHEMA public TO jpa_check_reader; ' +
    'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO jpa_check_reader');

  await test('exactly ten parent columns; required provenance has no insert defaults', async () => {
    const columns = (await db.query("SELECT column_name,is_nullable,column_default,data_type " +
      "FROM information_schema.columns WHERE table_schema='public' AND table_name='job_postings_analyses'")).rows;
    assert.deepEqual(columns.map(c => c.column_name).sort(), ['job_posting_id', 'job_family', 'seniority',
      'role_overview', 'role_overview_evidence', 'benefits', 'other_relevant_information',
      'source_content_hash', 'agent_version', 'analyzed_at'].sort());
    for (const field of ['agent_version', 'analyzed_at']) {
      const column = columns.find(c => c.column_name === field);
      assert.equal(column.is_nullable, 'NO');
      assert.equal(column.column_default, null);
      await reject(() => parent({ [field]: null }), '23502');
      const row = { job_posting_id: job, agent_version: '13', analyzed_at: analyzedAt };
      delete row[field];
      await reject(() => insert('job_postings_analyses', row), '23502');
    }
    assert.equal(columns.find(c => c.column_name === 'analyzed_at').data_type, 'timestamp with time zone');
    const row = (await parent()).rows[0];
    assert.equal(row.agent_version, '13');
    assert.equal(new Date(row.analyzed_at).toISOString(), analyzedAt);
    assert.deepEqual(row.role_overview_evidence, []);
    assert.deepEqual(row.other_relevant_information, []);
    await reject(() => parent(), '23505');
    await reject(() => parent({ job_posting_id: missing }), '23503');
  });
  await test('parent enum and evidence coupling checks', async () => {
    for (const field of ['job_family', 'seniority']) await reject(() => parent({ [field]: 'invented' }));
    await reject(() => parent({ role_overview_evidence: JSON.stringify(evidence) }));
    await reject(() => parent({ role_overview: 'Python or Go.' }));
    await reject(() => parent({ role_overview: ' ', role_overview_evidence: JSON.stringify(evidence) }));
    await reject(() => parent({ other_relevant_information: [null] }));
    await parent({ job_family: null, seniority: null, role_overview: 'Python or Go.',
      role_overview_evidence: JSON.stringify(evidence) });
  });
  await test('all five children preserve evidence, alternatives, unique positions and independent IDs', async () => {
    await parent();
    const ids = [];
    for (const table of children) {
      const row = (await child(table)).rows[0];
      ids.push(row.id);
      assert.equal(row.value, 'Python or Go.');
      assert.deepEqual(row.evidence, evidence);
      await reject(() => child(table), '23505');
      await child(table, { position: 1 });
      await reject(() => child(table, { job_posting_id: missing }), '23503');
      await reject(() => child(table, { position: -1 }));
      await reject(() => child(table, { position: 2, value: ' ' }));
      for (const value of ['[]', '{}', 'null']) {
        await reject(() => child(table, { position: 2, evidence: value }));
      }
    }
    assert.equal(new Set(ids).size, 5);
  });
  await test('qualification, condition and compensation domains', async () => {
    await parent();
    await reject(() => child('job_analysis_qualifications', { level: 'mandatory' }));
    for (const categories of [[], ['invented'], ['skill', null]]) {
      await reject(() => child('job_analysis_qualifications', { categories }));
    }
    await reject(() => child('job_analysis_conditions', { type: 'invented' }));
    await reject(() => child('job_analysis_compensation', { type: 'invented' }));
    await reject(() => child('job_analysis_compensation', { interval: 'invented' }));
    for (const value of ['-1', 'NaN', 'Infinity', '-Infinity']) {
      await reject(() => child('job_analysis_compensation', { minimum: value }));
      await reject(() => child('job_analysis_compensation', { maximum: value }));
    }
    await reject(() => child('job_analysis_compensation', { minimum: '20', maximum: '10' }));
    await child('job_analysis_compensation');
    assert.equal((await db.query('SELECT minimum::text AS amount FROM job_analysis_compensation')).rows[0].amount,
      '123456.123456789');
    await child('job_analysis_compensation', { position: 1, minimum: null, maximum: null });
  });
  await test('JOIN reads current source; closure and hash changes do not rewrite analysis provenance', async () => {
    await parent();
    const query = 'SELECT p.title,p.company_name,a.source_content_hash,a.agent_version,a.analyzed_at,' +
      'a.source_content_hash IS DISTINCT FROM p.content_hash AS stale ' +
      'FROM job_postings_analyses a JOIN job_postings p ON p.id=a.job_posting_id ' +
      "WHERE p.closed_at IS NULL AND a.job_family='ai_engineer' AND a.seniority='intern'";
    assert.equal((await db.query(query)).rows[0].stale, false);
    await db.query("UPDATE job_postings SET title='Updated title',company_name='Updated company',content_hash='synthetic-v2' WHERE id=$1", [job]);
    const row = (await db.query(query)).rows[0];
    assert.equal(row.title, 'Updated title');
    assert.equal(row.company_name, 'Updated company');
    assert.equal(row.stale, true);
    assert.equal(row.source_content_hash, 'synthetic-v1');
    assert.equal(row.agent_version, '13');
    assert.equal(new Date(row.analyzed_at).toISOString(), analyzedAt);
    await db.query('UPDATE job_postings SET closed_at=now() WHERE id=$1', [job]);
    assert.equal((await db.query(query)).rows.length, 0);
    assert.equal((await db.query('SELECT count(*)::int AS n FROM job_postings_analyses')).rows[0].n, 1);
  });
  await test('source deletion cascades through the parent and all five children', async () => {
    await parent();
    for (const table of children) await child(table);
    await db.query('DELETE FROM job_postings WHERE id=$1', [job]);
    for (const table of tables) {
      assert.equal((await db.query('SELECT count(*)::int AS n FROM ' + table)).rows[0].n, 0);
    }
  });
  await test('RLS blocks ordinary-role reads and inserts with no policies despite table privileges', async () => {
    await parent();
    for (const table of children) await child(table);
    const flags = (await db.query('SELECT relname,relrowsecurity FROM pg_class WHERE relname=ANY($1::text[])', [tables])).rows;
    assert.equal(flags.length, 6);
    assert.ok(flags.every(row => row.relrowsecurity));
    assert.equal((await db.query('SELECT count(*)::int AS n FROM pg_policies WHERE tablename=ANY($1::text[])', [tables])).rows[0].n, 0);
    await db.exec('SET LOCAL ROLE jpa_check_reader');
    for (const table of tables) {
      assert.equal((await db.query('SELECT count(*)::int AS n FROM ' + table)).rows[0].n, 0);
    }
    await reject(() => parent(), '42501');
    for (const table of children) await reject(() => child(table, { position: 1 }), '42501');
    await db.exec('RESET ROLE');
  });
  await db.exec(sql.downgrade);
  for (const table of tables) assert.equal((await db.query('SELECT to_regclass($1) AS t', [table])).rows[0].t, null);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM job_postings')).rows[0].n, 1);
  assert.ok((await db.query("SELECT to_regclass('resumes') AS t")).rows[0].t);
  console.log('PASS downgrade removes only six analysis tables and retains the source row and resume table');
  passed++;
  await db.exec(sql.upgrade_only);
  console.log('PASS re-upgrade after downgrade');
  passed++;
  console.log('TOTAL', passed, 'isolated PostgreSQL checks passed');
} finally {
  await db.close();
}
