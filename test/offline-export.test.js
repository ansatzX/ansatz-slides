import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { join, resolve } from 'node:path';
import test from 'node:test';

const root = resolve(import.meta.dirname, '..');
const exporter = join(root, 'skills/ansatz-slide/scripts/local-export/export-pptd.mjs');
const fixture = join(root, 'skills/ansatz-slide/tests/fixtures/minimal');
const denyNetwork = 'data:text/javascript,' + encodeURIComponent(
  'globalThis.fetch = () => { throw new Error("Unexpected network request in local export"); };'
);

test('direct exporter works without a remote signature or network, with and without the legacy flag', () => {
  mkdirSync(join(root, 'tmp'), { recursive: true });
  const dir = mkdtempSync(join(root, 'tmp/offline-export-'));
  try {
    for (const flags of [[], ['--no-sign']]) {
      const output = join(dir, flags.length ? 'compat.pptx' : 'default.pptx');
      const result = spawnSync(process.execPath, ['--import', denyNetwork, exporter, fixture, '-o', output, ...flags], { encoding: 'utf8' });
      assert.equal(result.status, 0, result.stdout + result.stderr);
      assert.equal(readFileSync(output).subarray(0, 2).toString(), 'PK');
      assert.match(result.stdout, /local writer token/);
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('removed remote-authentication options fail explicitly', () => {
  for (const flag of ['--cookie', '--origin']) {
    const result = spawnSync(process.execPath, [exporter, fixture, flag, 'unused'], { encoding: 'utf8' });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /Unknown arg/);
  }
});

test('local editor entrypoints expose the project identity rather than a legacy title or favicon', () => {
  for (const file of ['editor/index.html', 'editor/neo-ppt/index.html']) {
    const html = readFileSync(join(root, file), 'utf8');
    assert.match(html, /<title>ansatz-slide(?: editor)?<\/title>/);
    assert.match(html, /rel="icon" href="data:,"/);
  }
});
