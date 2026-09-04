import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve, relative, sep } from 'node:path';
import test from 'node:test';

const skill = resolve(import.meta.dirname, '../skills/ansatz-slide');
const entrypoints = [
  'SKILL.md', 'reference/agent-contract.md', 'reference/authoring-start.md',
  'reference/operations.md', 'reference/page-edit.md', 'reference/delivery-checks.md',
  'reference/slides_categories.md', 'reference/general-poster.md',
  'reference/slides_categories/academic-research.md',
  'reference/slides_categories/analysis-decision.md',
  'reference/slides_categories/business-plan.md',
  'reference/slides_categories/management-report.md',
  'reference/slides_categories/education-training.md',
  'reference/slides_categories/tech-engineering.md',
  'reference/slides_categories/brand-creative.md',
  'reference/design-system-runtime.md', 'reference/design-system-inventory.md',
];

test('instruction entrypoints resolve their local references inside the distributable skill', () => {
  for (const entry of entrypoints) {
    const file = resolve(skill, entry);
    const content = readFileSync(file, 'utf8');
    for (const [, target] of content.matchAll(/\[[^\]]+\]\(([^)]+)\)/g)) {
      if (/^(?:https?:|#)/.test(target)) continue;
      const resolved = resolve(dirname(file), target.split('#')[0]);
      const rel = relative(skill, resolved);
      assert.ok(rel !== '..' && !rel.startsWith(`..${sep}`), `${entry}: outside skill ${target}`);
      assert.ok(existsSync(resolved), `${entry}: missing ${target}`);
    }
  }
});
