import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join, resolve } from "node:path";
import test from "node:test";

const projectRoot = resolve(import.meta.dirname, "..");
const cli = join(projectRoot, "bin", "ansatz-slide.js");
const fixture = join(projectRoot, "skills", "ansatz-slide", "tests", "fixtures", "minimal");
const boundaryFixture = join(projectRoot, "skills", "ansatz-slide", "tests", "fixtures", "boundary-capabilities");
const taskTmp = join(projectRoot, "tmp");

function run(args) {
  return spawnSync(process.execPath, [cli, ...args], {
    cwd: projectRoot,
    encoding: "utf8",
    env: { ...process.env, TMPDIR: taskTmp },
  });
}

test("CLI validates a complete PPTD project", () => {
  const result = run(["validate", fixture]);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /PPTD valid: 1 page/);
});

test("CLI exports through the pure Node validator and WASM path", () => {
  mkdirSync(taskTmp, { recursive: true });
  const outputDir = mkdtempSync(join(taskTmp, "ansatz-slide-cli-"));
  const output = join(outputDir, "minimal.pptx");
  try {
    const result = run(["export", fixture, "--output", output]);
    assert.equal(result.status, 0, result.stderr || result.stdout);
    assert.equal(existsSync(output), true);
  } finally {
    rmSync(outputDir, { recursive: true, force: true });
  }
});

test("all bundled example projects satisfy the executable DSL", () => {
  for (const example of [
    boundaryFixture,
    join(projectRoot, "example", "dji-pocket4"),
    join(projectRoot, "example", "xiaomi-yu7-ppt-animation"),
    join(projectRoot, "example", "yu7-ppt"),
  ]) {
    const result = run(["validate", example]);
    assert.equal(result.status, 0, `${example}\n${result.stderr || result.stdout}`);
  }
});

test("pure Node export resolves image fills nested inside table cells", () => {
  mkdirSync(taskTmp, { recursive: true });
  const project = mkdtempSync(join(taskTmp, "nested-image-fill-"));
  const output = join(project, "nested.pptx");
  try {
    writeFileSync(join(project, "deck.pptd"), "version: v2\ntitle: nested image\nsize: [960, 540]\npages: [pages/1.page]\n");
    mkdirSync(join(project, "pages"));
    writeFileSync(join(project, "pages", "1.page"), `elements:
  - elementId: table
    elementType: table
    bounds: [100, 100, 400, 200]
    columnWidths: [1]
    rowHeights: [1]
    rows:
      - - text: nested
          fill: {type: image, src: pixel.png}
`);
    writeFileSync(join(project, "pixel.png"), Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z1xkAAAAASUVORK5CYII=", "base64"));
    const result = run(["export", project, "--output", output]);
    assert.equal(result.status, 0, result.stderr || result.stdout);
    assert.match(result.stdout, /1 image\(s\)/);
    assert.equal(existsSync(output), true);
  } finally {
    rmSync(project, { recursive: true, force: true });
  }
});
