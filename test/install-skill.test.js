import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const cli = join(projectRoot, "bin", "ansatz-slide.js");
const taskTmp = join(projectRoot, "tmp");

function tempRoot() {
  mkdirSync(taskTmp, { recursive: true });
  return mkdtempSync(join(taskTmp, "ansatz-slide-test-"));
}

function runCli(args, env = process.env) {
  return spawnSync(process.execPath, [cli, ...args], {
    encoding: "utf8",
    env,
  });
}

test("installs the packaged skill into a custom skills directory", () => {
  const root = tempRoot();
  const target = join(root, "skills");

  try {
    const result = runCli(["install", "--target", target]);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(existsSync(join(target, "ansatz-slide", "SKILL.md")), true);
    assert.equal(existsSync(join(target, "ansatz-slide", "scripts", "export_pptx.py")), true);
    assert.equal(
      existsSync(join(target, "ansatz-slide", "scripts", "local-export", "pptd_wasm_bg.wasm")),
      true,
    );
    assert.equal(
      existsSync(join(target, "ansatz-slide", "node_modules", "yaml", "package.json")),
      true,
    );
    assert.equal(existsSync(join(target, "ansatz-slide", "pyproject.toml")), true);
    assert.equal(existsSync(join(target, "ansatz-slide", "uv.lock")), true);
    assert.equal(
      existsSync(join(target, "ansatz-slide", "editor", "index.html")),
      true,
    );
    assert.equal(existsSync(join(target, "ansatz-slide", "_user_meta.json")), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("installs into ~/.agents/skills when no target is provided (non-interactive)", () => {
  const root = tempRoot();

  try {
    const result = runCli([], { ...process.env, HOME: root, USERPROFILE: root, CODEX_HOME: undefined });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(existsSync(join(root, ".agents", "skills", "ansatz-slide", "SKILL.md")), true);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("supports -y for non-interactive default install", () => {
  const root = tempRoot();

  try {
    const result = runCli(["install", "-y"], {
      ...process.env,
      HOME: root,
      USERPROFILE: root,
      CODEX_HOME: undefined,
    });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(existsSync(join(root, ".agents", "skills", "ansatz-slide", "SKILL.md")), true);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("installs into multiple --target directories", () => {
  const root = tempRoot();
  const first = join(root, "codex", "skills");
  const second = join(root, "claude", "skills");

  try {
    const result = runCli(["install", "--target", first, "--target", second]);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(existsSync(join(first, "ansatz-slide", "SKILL.md")), true);
    assert.equal(existsSync(join(second, "ansatz-slide", "SKILL.md")), true);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("--all installs into detected agent directories and skips missing ones", () => {
  const root = tempRoot();

  try {
    mkdirSync(join(root, ".agents"), { recursive: true });
    mkdirSync(join(root, ".codex"), { recursive: true });
    mkdirSync(join(root, ".claude"), { recursive: true });

    const result = runCli(["install", "--all"], {
      ...process.env,
      HOME: root,
      USERPROFILE: root,
      CODEX_HOME: undefined,
    });
    assert.equal(result.status, 0, result.stderr);

    for (const relative of [[".agents", "skills"], [".codex", "skills"], [".claude", "skills"]]) {
      assert.equal(
        existsSync(join(root, ...relative, "ansatz-slide", "SKILL.md")),
        true,
        relative.join("/"),
      );
    }
    for (const missing of [".cursor", ".workbuddy"]) {
      assert.equal(existsSync(join(root, missing)), false, missing);
    }
    assert.match(result.stdout, /Skipped .*\.cursor/);
    assert.match(result.stdout, /Skipped .*\.workbuddy/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("--all warns and installs nothing when no agent directory exists", () => {
  const root = tempRoot();

  try {
    const result = runCli(["install", "--all"], {
      ...process.env,
      HOME: root,
      USERPROFILE: root,
      CODEX_HOME: undefined,
    });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(existsSync(join(root, ".agents")), false);
    assert.match(result.stderr, /No known agent directories found/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("overwrites an existing installation by default", () => {
  const root = tempRoot();
  const target = join(root, "skills");
  const skillFile = join(target, "ansatz-slide", "SKILL.md");

  try {
    assert.equal(runCli(["--target", target]).status, 0);
    writeFileSync(skillFile, "modified", "utf8");

    const result = runCli(["--target", target]);
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /Updated ansatz-slide/);
    assert.match(readFileSync(skillFile, "utf8"), /^---\nname: ansatz-slide/m);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("accepts legacy --force without changing overwrite behavior", () => {
  const root = tempRoot();
  const target = join(root, "skills");

  try {
    assert.equal(runCli(["--target", target]).status, 0);
    const result = runCli(["--target", target, "--force"]);
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /Updated ansatz-slide/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("help documents interactive install and -y for agents", () => {
  const result = runCli(["install", "--help"]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /space select/);
  assert.match(result.stdout, /-y, --yes/);
  assert.match(result.stdout, /--all/);
  assert.match(result.stdout, /npx ansatz-slide@latest install -y/);
});

test("-h shows help", () => {
  const result = runCli(["-h"]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Usage:/);
  assert.match(result.stdout, /-h, --help/);
  assert.match(result.stdout, /-V, --version/);
});

test("--version and -V print the package version", () => {
  const { version } = JSON.parse(readFileSync(join(projectRoot, "package.json"), "utf8"));
  for (const args of [["--version"], ["-V"], ["serve", "--version"]]) {
    const result = runCli(args);
    assert.equal(result.status, 0, `${args.join(" ")}: ${result.stderr}`);
    assert.equal(result.stdout.trim(), version);
  }
});
