import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { validatePptdProject } from '../skills/ansatz-slide/scripts/local-export/validate-pptd.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ref = path.join(root, 'skills/ansatz-slide/reference');
const examples = path.join(root, 'example/verified-styles');
function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e =>
    e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]);
}
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));

test('every preset links to the runtime contract and is present in the inventory', () => {
  const styles = walk(path.join(ref, 'design_system')).filter(p => p.endsWith('.md'));
  assert.equal(styles.length, 60);
  const inventory = fs.readFileSync(path.join(ref, 'design-system-inventory.md'), 'utf8');
  for (const style of styles) {
    const content = fs.readFileSync(style, 'utf8');
    const match = content.match(/\[design-system-runtime\.md\]\(([^)]+)\)/);
    assert.ok(match, style);
    assert.equal(path.resolve(path.dirname(style), match[1]), path.join(ref, 'design-system-runtime.md'));
    assert.ok(inventory.includes(path.relative(ref, style)), style);
    assert.ok(!content.includes('`fit: cover`'), style);
    assert.ok(!content.includes('`crop: {top, bottom}`'), style);
  }
});

test('five showcase sources validate, use external evidence and retain native text', () => {
  const ids = read(path.join(examples, 'projects.json'));
  assert.equal(ids.length, 5);
  for (const id of ids) {
    const dir = path.join(examples, id);
    const manifest = read(path.join(dir, 'deck.pptd'));
    const pages = manifest.pages.map(p => ({ path: p, data: read(path.join(dir, p)) }));
    assert.equal(validatePptdProject({ manifest, pages }, { projectRoot: dir, checkFiles: true }).ok, true);
    const elements = pages[0].data.elements;
    assert.equal(elements.filter(e => e.elementType === 'image').length, 1);
    assert.ok(elements.filter(e => e.elementType === 'text').length >= 5);
    assert.ok(elements.every(e => ['image', 'shape', 'text'].includes(e.elementType)));
    const provenance = read(path.join(dir, 'provenance.json'));
    assert.ok(fs.existsSync(path.join(root, provenance.style)));
    for (const file of ['media/evidence.png', 'data.json', 'demo.pptx', 'preview.png']) {
      assert.ok(fs.statSync(path.join(dir, file)).size > 0);
    }
  }
});

test('corrected image syntax passes; scalar fit and native text opacity still fail', () => {
  const manifest = { version: 'v2', title: 'Contract', size: [960,540], pages: ['1.page'] };
  const project = element => ({ manifest, pages: [{ path: '1.page', data: { elements: [element] } }] });
  const image = { elementId: 'image', elementType: 'image', bounds: [20,20,200,100],
    src: 'data:image/png;base64,AA==', fit: { mode: 'cover' }, crop: { top: 0.2, bottom: 0.2 } };
  assert.doesNotThrow(() => validatePptdProject(project(image)));
  assert.throws(() => validatePptdProject(project({ ...image, fit: 'cover' })), /fit/);
  const text = { elementId: 'text', elementType: 'text', bounds: [20,20,200,100], content: { text: '01' } };
  assert.doesNotThrow(() => validatePptdProject(project(text)));
  assert.throws(() => validatePptdProject(project({ ...text, opacity: 0.2 })), /not preserved/);
});

test('illustrative figures reconcile with their explicit data basis', () => {
  const finance = read(path.join(examples,'black-gold-ledger/data.json'));
  assert.equal(finance.rows.reduce((s,r) => s+r[1],0), finance.plan_total);
  assert.equal(finance.rows.reduce((s,r) => s+r[2],0), finance.actual_total);
  assert.equal(finance.plan_total-finance.actual_total, 6);
  const work = read(path.join(examples,'blue-flame-brand/data.json'));
  assert.equal(work.actual.at(-1)/work.w8_target, 1);
  assert.equal(read(path.join(examples,'cream-collage/data.json')).beats.length, 7);
});
