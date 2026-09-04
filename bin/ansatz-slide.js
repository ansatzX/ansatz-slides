#!/usr/bin/env node

import { cpSync, existsSync, mkdtempSync, mkdirSync, readFileSync, renameSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, join, resolve, sep } from "node:path";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { stdin as input, stdout as output } from "node:process";
import { fileURLToPath } from "node:url";
import { startEditorServer } from "../lib/editor-server.js";

const SKILL_NAME = "ansatz-slide";
const MIN_NODE_MAJOR = 24;
const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
const sourceDirectory = join(packageRoot, "skills", SKILL_NAME);
const packageVersion = JSON.parse(readFileSync(join(packageRoot, "package.json"), "utf8")).version;

const KNOWN_TARGETS = [
  { id: "agents", label: "Shared / default", relative: [".agents", "skills"] },
  { id: "codex", label: "Codex", relative: [".codex", "skills"] },
  { id: "claude", label: "Claude Code", relative: [".claude", "skills"] },
  { id: "cursor", label: "Cursor", relative: [".cursor", "skills"] },
  { id: "workbuddy", label: "WorkBuddy", relative: [".workbuddy", "skills"] },
];

function assertNodeVersion() {
  const major = Number.parseInt(process.versions.node.split(".")[0], 10);
  if (!Number.isInteger(major) || major < MIN_NODE_MAJOR) {
    throw new Error(
      `Node.js ${MIN_NODE_MAJOR}+ is required; found ${process.version}. Install from https://nodejs.org`,
    );
  }
}

function printHelp(command) {
  if (command === "export" || command === "validate" || command === "incremental") {
    if (command === "incremental") {
      console.log(`Replace exactly one slide in an existing PPTX while preserving non-target slide semantics.

Usage:
  ansatz-slide incremental <baseline.pptx> <project|deck.pptd> --page <1-based-index> -o result.pptx
`);
      return;
    }
    console.log(command === "export"
      ? `Export a validated PPTD project with the bundled local WASM writer.\n\nUsage:\n  ansatz-slide export <project|deck.pptd> [-o deck.pptx] [--transition fade|none]\n`
      : `Validate a complete PPTD project without writing a PPTX.\n\nUsage:\n  ansatz-slide validate <project|deck.pptd>\n`);
    return;
  }
  if (command === "serve") {
    console.log(`Start the local PPTD editor and exporter.

Usage:
  ansatz-slide serve [options]

Options:
  --port <number>  HTTP port (default: 55173)
  --open           Open the editor in the default browser
  -h, --help       Show this help
  -V, --version    Show version
`);
    return;
  }

  console.log(`Install ${SKILL_NAME} for your AI coding agent or start its local editor.

Usage:
  ansatz-slide [install] [options]
  ansatz-slide serve [options]
  ansatz-slide validate <project|deck.pptd>
  ansatz-slide export <project|deck.pptd> [-o deck.pptx]
  ansatz-slide incremental <baseline.pptx> <project|deck.pptd> --page <n> -o result.pptx

Install options:
  --target <directory>  Skills directory (repeatable)
  -y, --yes             Non-interactive; install to ~/.agents/skills when no --target
  --all                 Install to all detected agent skill directories
                        (agents whose home directory is missing are skipped)
  -h, --help            Show this help
  -V, --version         Show version

In an interactive terminal (no --target / --yes / --all), a checklist is shown:
  ↑/↓ move  space select  a all  enter confirm

For agents / CI, prefer:
  npx ansatz-slide@latest install -y

Re-running install replaces an existing ansatz-slide installation.
Run "ansatz-slide serve --help" for server options.
`);
}

function printVersion() {
  console.log(packageVersion);
}

function parseArguments(arguments_) {
  const args = [...arguments_];
  const commands = new Set(["install", "serve", "validate", "export", "incremental"]);
  const command = commands.has(args[0]) ? args.shift() : "install";
  if (command === "validate" || command === "export" || command === "incremental") {
    const help = args.includes("--help") || args.includes("-h");
    const version = args.includes("--version") || args.includes("-V");
    return { command, passthrough: args, help, version };
  }
  const options = command === "serve"
    ? { command, open: false, port: 55173 }
    : { command, targets: [], yes: false, all: false };

  while (args.length > 0) {
    const argument = args.shift();

    // Accepted for backward compatibility; install always overwrites.
    if (command === "install" && argument === "--force") {
      continue;
    }

    if (command === "install" && (argument === "-y" || argument === "--yes")) {
      options.yes = true;
      continue;
    }

    if (command === "install" && argument === "--all") {
      options.all = true;
      continue;
    }

    if (command === "install" && argument === "--target") {
      const target = args.shift();
      if (!target || target.startsWith("-")) {
        throw new Error("--target requires a directory");
      }
      options.targets.push(resolve(target));
      continue;
    }

    if (command === "serve" && argument === "--port") {
      const port = Number(args.shift());
      if (!Number.isInteger(port) || port < 1 || port > 65_535) {
        throw new Error("--port must be an integer between 1 and 65535");
      }
      options.port = port;
      continue;
    }

    if (command === "serve" && argument === "--open") {
      options.open = true;
      continue;
    }

    if (argument === "--help" || argument === "-h") {
      options.help = true;
      continue;
    }

    if (argument === "--version" || argument === "-V") {
      options.version = true;
      continue;
    }

    throw new Error(`unknown argument: ${argument}`);
  }

  return options;
}

function runLocalExporter(arguments_) {
  const exporter = join(sourceDirectory, "scripts", "local-export", "export-pptd.mjs");
  if (!existsSync(exporter)) throw new Error(`local exporter is missing: ${exporter}`);
  const args = [...arguments_];
  if (!args.includes("--no-sign")) args.push("--no-sign");
  return new Promise((resolvePromise, reject) => {
    const child = spawn(process.execPath, [exporter, ...args], { stdio: "inherit" });
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (signal) reject(new Error(`local exporter stopped by signal ${signal}`));
      else if (code === 0) resolvePromise();
      else reject(new Error(`local exporter exited with status ${code}`));
    });
  });
}

function runIncrementalExporter(arguments_) {
  const script = join(sourceDirectory, "scripts", "incremental_replace_pptx.py");
  if (!existsSync(script)) throw new Error(`incremental exporter is missing: ${script}`);
  const python = process.platform === "win32" ? "python" : "python3";
  return new Promise((resolvePromise, reject) => {
    const child = spawn(python, [script, ...arguments_], { stdio: "inherit" });
    child.once("error", (error) => reject(new Error(`could not start ${python}: ${error.message}`)));
    child.once("exit", (code, signal) => {
      if (signal) reject(new Error(`incremental exporter stopped by signal ${signal}`));
      else if (code === 0) resolvePromise();
      else reject(new Error(`incremental exporter exited with status ${code}`));
    });
  });
}

function openBrowser(url) {
  const command = process.platform === "darwin" ? "open" : process.platform === "win32" ? "cmd" : "xdg-open";
  const args = process.platform === "win32" ? ["/c", "start", "", url] : [url];
  const child = spawn(command, args, { detached: true, stdio: "ignore" });
  child.on("error", (error) => console.warn(`Could not open the browser: ${error.message}`));
  child.unref();
}

function defaultSkillsDirectory() {
  return join(homedir(), ".agents", "skills");
}

function knownTargetDirectories() {
  const home = homedir();
  return KNOWN_TARGETS.map((entry) => ({
    ...entry,
    directory: join(home, ...entry.relative),
  }));
}

function displayPath(absolutePath) {
  const home = homedir();
  const normalized = absolutePath.split(sep).join("/");
  const homeNormalized = home.split(sep).join("/");
  if (normalized === homeNormalized || normalized.startsWith(`${homeNormalized}/`)) {
    return `~${normalized.slice(homeNormalized.length)}`;
  }
  return absolutePath;
}

function isInteractiveInstall() {
  return Boolean(input.isTTY && output.isTTY);
}

function uniqueDirectories(directories) {
  const seen = new Set();
  const unique = [];
  for (const directory of directories) {
    const key = resolve(directory);
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(key);
  }
  return unique;
}

async function promptInstallTargets() {
  const choices = knownTargetDirectories();
  const selected = new Set([0]);
  let cursor = 0;
  // title + help + one line per choice (must match what render() writes)
  const lines = choices.length + 2;

  const writeLine = (text) => {
    output.write(`\u001b[2K${text}\n`);
  };

  const render = (initial = false) => {
    if (!initial) {
      output.write(`\u001b[${lines}A`);
    }
    writeLine("Install ansatz-slide to which skills directories?");
    writeLine("↑/↓ move · space select · a all · enter confirm · ctrl+c cancel");
    for (const [index, choice] of choices.entries()) {
      const pointer = index === cursor ? "❯" : " ";
      const mark = selected.has(index) ? "◉" : "◯";
      const installed = existsSync(join(choice.directory, SKILL_NAME, "SKILL.md"))
        ? " (installed)"
        : "";
      writeLine(
        `${pointer}${mark} ${displayPath(choice.directory).padEnd(28)} ${choice.label}${installed}`,
      );
    }
  };

  return new Promise((resolvePromise, reject) => {
    if (typeof input.setRawMode !== "function") {
      resolvePromise([defaultSkillsDirectory()]);
      return;
    }

    render(true);
    input.setRawMode(true);
    input.resume();
    input.setEncoding("utf8");

    const cleanup = () => {
      input.off("data", onData);
      input.setRawMode(false);
      input.pause();
    };

    const onData = (key) => {
      if (key === "\u0003") {
        cleanup();
        output.write("\n");
        reject(new Error("install cancelled"));
        return;
      }

      if (key === "\u001b[A" || key === "k") {
        cursor = (cursor - 1 + choices.length) % choices.length;
        render();
        return;
      }

      if (key === "\u001b[B" || key === "j") {
        cursor = (cursor + 1) % choices.length;
        render();
        return;
      }

      if (key === " ") {
        if (selected.has(cursor)) selected.delete(cursor);
        else selected.add(cursor);
        render();
        return;
      }

      if (key === "a" || key === "A") {
        if (selected.size === choices.length) selected.clear();
        else for (let index = 0; index < choices.length; index += 1) selected.add(index);
        render();
        return;
      }

      if (key === "\r" || key === "\n") {
        if (selected.size === 0) {
          output.write("\u0007");
          return;
        }
        cleanup();
        output.write("\n");
        resolvePromise([...selected].sort((a, b) => a - b).map((index) => choices[index].directory));
      }
    };

    input.on("data", onData);
  });
}

function detectedTargetDirectories() {
  const home = homedir();
  const detected = [];
  const skipped = [];
  for (const entry of knownTargetDirectories()) {
    if (existsSync(join(home, entry.relative[0]))) detected.push(entry);
    else skipped.push(entry);
  }
  return { detected, skipped };
}

async function resolveInstallTargets(options) {
  if (options.targets.length > 0) {
    return uniqueDirectories(options.targets);
  }

  if (options.all) {
    const { detected, skipped } = detectedTargetDirectories();
    for (const entry of skipped) {
      console.log(`Skipped ${entry.directory} (${entry.label} not found)`);
    }
    if (detected.length === 0) {
      console.warn(
        "No known agent directories found; nothing installed. Use -y for ~/.agents/skills or --target <directory>.",
      );
    }
    return uniqueDirectories(detected.map((entry) => entry.directory));
  }

  if (options.yes || !isInteractiveInstall()) {
    return [defaultSkillsDirectory()];
  }

  return promptInstallTargets();
}

const CANONICAL_WASM = join(
  packageRoot,
  "editor",
  "neo-ppt",
  "assets",
  "pptd_wasm_bg-DPPWdROu.wasm",
);
const PACKAGED_YAML = dirname(require.resolve("yaml/package.json"));
const PYTHON_RUNTIME_FILES = ["pyproject.toml", "uv.lock"];

function installSkillTo(skillsDirectory) {
  if (!existsSync(join(sourceDirectory, "SKILL.md"))) {
    throw new Error(`packaged skill is incomplete: ${sourceDirectory}`);
  }
  if (!existsSync(CANONICAL_WASM)) {
    throw new Error(`packaged patched WASM is missing: ${CANONICAL_WASM}`);
  }
  if (!existsSync(join(PACKAGED_YAML, "package.json"))) {
    throw new Error("packaged yaml runtime dependency is missing; reinstall ansatz-slide");
  }

  const destination = join(skillsDirectory, SKILL_NAME);
  const replaced = existsSync(destination);

  mkdirSync(skillsDirectory, { recursive: true });
  const stagingRoot = mkdtempSync(join(skillsDirectory, `.${SKILL_NAME}-`));
  const stagedSkill = join(stagingRoot, SKILL_NAME);

  try {
    cpSync(sourceDirectory, stagedSkill, {
      recursive: true,
      filter: (source) => ![".DS_Store", "_user_meta.json"].includes(basename(source)),
    });
    // Single canonical WASM in editor/; copy into skill tree for agent scripts.
    const stagedWasmDir = join(stagedSkill, "scripts", "local-export");
    mkdirSync(stagedWasmDir, { recursive: true });
    cpSync(CANONICAL_WASM, join(stagedWasmDir, "pptd_wasm_bg.wasm"));
    // The copied skill must remain runnable after the transient npx process
    // exits. Vendor the small, pure-JavaScript YAML parser beside the scripts.
    mkdirSync(join(stagedSkill, "node_modules"), { recursive: true });
    cpSync(PACKAGED_YAML, join(stagedSkill, "node_modules", "yaml"), {
      recursive: true,
      filter: (source) => basename(source) !== ".DS_Store",
    });
    // Keep optional Python compatibility and visual-QA dependencies locked
    // inside the installed skill. Core validation/export does not use them.
    for (const filename of PYTHON_RUNTIME_FILES) {
      const source = join(packageRoot, filename);
      if (!existsSync(source)) throw new Error(`packaged Python runtime file is missing: ${source}`);
      cpSync(source, join(stagedSkill, filename));
    }
    // Offline image/PPTX browser path needs the local neo-ppt mirror.
    const packagedEditor = join(packageRoot, "editor");
    if (!existsSync(join(packagedEditor, "index.html"))) {
      throw new Error(`packaged editor is missing: ${packagedEditor}`);
    }
    cpSync(packagedEditor, join(stagedSkill, "editor"), {
      recursive: true,
      filter: (source) => basename(source) !== ".DS_Store",
    });

    rmSync(destination, { recursive: true, force: true });
    renameSync(stagedSkill, destination);
  } finally {
    rmSync(stagingRoot, { recursive: true, force: true });
  }

  console.log(
    replaced
      ? `Updated ${SKILL_NAME} at ${destination}`
      : `Installed ${SKILL_NAME} to ${destination}`,
  );
}

async function installSkill(options) {
  const targets = await resolveInstallTargets(options);
  for (const target of targets) {
    installSkillTo(target);
  }
}

async function main() {
  assertNodeVersion();
  const options = parseArguments(process.argv.slice(2));
  if (options.version) {
    printVersion();
    return;
  }
  if (options.help) {
    printHelp(options.command);
    return;
  }

  if (options.command === "install") {
    await installSkill(options);
    return;
  }

  if (options.command === "validate") {
    const passthrough = options.passthrough.filter((value) => !["--help", "-h", "--version", "-V"].includes(value));
    if (passthrough.length !== 1) throw new Error("validate requires exactly one PPTD project or manifest");
    await runLocalExporter([...passthrough, "--validate-only"]);
    return;
  }

  if (options.command === "export") {
    const passthrough = options.passthrough.filter((value) => !["--help", "-h", "--version", "-V"].includes(value));
    if (passthrough.length === 0) throw new Error("export requires a PPTD project or manifest");
    await runLocalExporter(passthrough);
    return;
  }

  if (options.command === "incremental") {
    const passthrough = options.passthrough.filter((value) => !["--help", "-h", "--version", "-V"].includes(value));
    if (passthrough.length < 2 || passthrough[0].startsWith("-") || passthrough[1].startsWith("-")) {
      throw new Error("incremental requires <baseline.pptx> <project|deck.pptd> --page <n> --output <result.pptx>");
    }
    const [baseline, project, ...rest] = passthrough;
    await runIncrementalExporter(["--baseline", baseline, "--project", project, ...rest]);
    return;
  }

  const { server, url } = await startEditorServer({ port: options.port });
  console.log(`Ansatz Slide editor is running at ${url}`);
  console.log("Press Ctrl+C to stop the server.");
  if (options.open) openBrowser(url);

  const shutdown = () => server.close(() => process.exit(0));
  process.once("SIGINT", shutdown);
  process.once("SIGTERM", shutdown);
}

main().catch((error) => {
  console.error(`Error: ${error.message}`);
  process.exitCode = 1;
});
