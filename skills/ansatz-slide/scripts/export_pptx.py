#!/usr/bin/env python3
"""Export a PPTD project to PPTX.

Default path (preferred): local patched official WASM writer
  scripts/local-export/export-pptd.mjs --no-sign
  → offline, no cookie, no signature API, no browser UI.

Optional --browser path: local neo-ppt mirror via agent-browser
  (same UI as `npx ansatz-slide serve`, no remote editor service).

Image QA (`export_images.py`) uses the same local editor host.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
import zipfile
import xml.etree.ElementTree as ET
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

SKILL_DIR = Path(__file__).resolve().parent.parent
IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_EMBEDDED_MEDIA_BYTES = 200 * 1024 * 1024
PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
)
FADE_TRANSITION_XML = (
    '<p:transition spd="fast" advClick="1"><p:fade/></p:transition>'
)
MIN_AGENT_BROWSER_VERSION = (0, 34, 0)
MIN_NODE_MAJOR = 24
NODE_INSTALL_HINT = "Install Node.js 24+ from https://nodejs.org, then retry."
EDITOR_MISSING_HINT = (
    "local neo-ppt editor not found. Re-run "
    "`npx ansatz-slide install` (copies editor into the skill) "
    "or set ANSATZ_SLIDE_EDITOR to the editor directory."
)


class ExportError(RuntimeError):
    pass


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: Any) -> None:
        return


def log(message: str) -> None:
    print(f"[ansatz-slide] {message}", file=sys.stderr, flush=True)


def task_tmp_dir() -> Path:
    """Return the project-local scratch directory used by compatibility tools."""
    configured = os.environ.get("ANSATZ_SLIDE_TMPDIR")
    root = Path(configured).expanduser() if configured else Path.cwd() / "tmp"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def run_command(
    command: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: int = 90,
) -> subprocess.CompletedProcess[str]:
    """Capture merged stdout/stderr via a temp file.

    On Windows, agent-browser's detached daemon can inherit a PIPE handle and
    prevent EOF, deadlocking ``subprocess.run(stdout=PIPE)``. Decoding with the
    system locale (GBK on zh-CN Windows) can also raise UnicodeDecodeError.
    Writing to a UTF-8 file avoids both failures.
    """
    handle, sink_path = tempfile.mkstemp(
        prefix="ansatz-slide-", suffix=".log", dir=task_tmp_dir()
    )
    os.close(handle)
    sink = Path(sink_path)
    output = ""
    try:
        with sink.open("w", encoding="utf-8", errors="replace") as out:
            returncode = subprocess.call(
                list(command),
                cwd=str(cwd) if cwd is not None else None,
                env=env,
                stdout=out,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
        output = sink.read_text(encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        try:
            output = sink.read_text(encoding="utf-8", errors="replace")
        except OSError:
            output = ""
        raise subprocess.TimeoutExpired(
            cmd=list(command),
            timeout=timeout,
            output=output,
        ) from exc
    finally:
        try:
            sink.unlink(missing_ok=True)
        except OSError:
            # WinError 32: daemon may still hold the log file handle.
            pass
    return subprocess.CompletedProcess(list(command), returncode, output, None)


def temporary_directory(prefix: str) -> Any:
    # ignore_cleanup_errors avoids masking the real export error when a Windows
    # browser daemon still holds files under the temp tree (Python 3.10+).
    try:
        return tempfile.TemporaryDirectory(
            prefix=prefix, dir=task_tmp_dir(), ignore_cleanup_errors=True
        )
    except TypeError:
        return tempfile.TemporaryDirectory(prefix=prefix, dir=task_tmp_dir())


def default_downloads_dir() -> Path:
    home = Path.home()
    candidates: List[Path] = []
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidates.append(Path(user_profile) / "Downloads")
    candidates.extend((home / "Downloads", home / "下载"))
    for path in candidates:
        if path.is_dir():
            return path
    return home / "Downloads"


def ensure_pyyaml() -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise ExportError(
            "PyYAML is required by the compatibility Python wrapper. "
            "From the ansatz-slide repository run: uv sync --frozen"
        ) from exc
    return yaml


yaml = ensure_pyyaml()


def parse_version(output: str) -> Tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)\b", output)
    if not match:
        raise ExportError(f"could not parse agent-browser version from: {output.strip()}")
    return tuple(int(part) for part in match.groups())


def parse_node_version(output: str) -> Tuple[int, int, int]:
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)\b", output)
    if not match:
        raise ExportError(f"could not parse Node.js version from: {output.strip()}")
    return tuple(int(part) for part in match.groups())


def read_agent_browser_version(executable: str) -> Tuple[int, int, int]:
    process = run_command([executable, "--version"], timeout=30)
    if process.returncode != 0:
        raise ExportError(f"agent-browser --version failed:\n{process.stdout[-2000:]}")
    return parse_version(process.stdout)


def ensure_nodejs() -> str:
    executable = shutil.which("node")
    if not executable:
        raise ExportError(f"Node.js is not installed or not on PATH. {NODE_INSTALL_HINT}")

    process = run_command([executable, "--version"], timeout=30)
    if process.returncode != 0:
        raise ExportError(f"node --version failed:\n{process.stdout[-2000:]}")

    version = parse_node_version(process.stdout)
    if version[0] < MIN_NODE_MAJOR:
        raise ExportError(
            f"Node.js {MIN_NODE_MAJOR}+ is required; found "
            f"{'.'.join(map(str, version))} ({process.stdout.strip()}). {NODE_INSTALL_HINT}"
        )

    log(f"Node.js version: {'.'.join(map(str, version))}")
    return executable


def ensure_agent_browser() -> str:
    ensure_nodejs()

    configured = os.environ.get("ANSATZ_SLIDE_AGENT_BROWSER")
    repository_local = Path(__file__).resolve().parents[3] / "node_modules" / ".bin" / (
        "agent-browser.cmd" if os.name == "nt" else "agent-browser"
    )
    candidates = [configured, str(repository_local), shutil.which("agent-browser")]
    executable = next((item for item in candidates if item and Path(item).is_file()), None)
    version = read_agent_browser_version(executable) if executable else None
    if version is not None and version >= MIN_AGENT_BROWSER_VERSION:
        log(f"agent-browser version: {'.'.join(map(str, version))}")
        return executable

    current = "not installed" if version is None else ".".join(map(str, version))
    minimum = ".".join(map(str, MIN_AGENT_BROWSER_VERSION))
    raise ExportError(
        f"agent-browser {current}; version {minimum} is required for visual QA. "
        "Install it locally with `npm install --no-save agent-browser@0.34.0` "
        "or set ANSATZ_SLIDE_AGENT_BROWSER. No global install or Chromium "
        "download is performed; an existing system Chrome is used."
    )


DEBUG_CHROME_PORT = 9337
CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def cdp_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2):
            return True
    except OSError:
        return False


def ensure_debug_chrome() -> Optional[int]:
    """Return a CDP port for agent-browser to connect to (Windows only).

    On Windows agent-browser cannot launch Chrome itself: the Chrome launcher
    process hands off to a child and exits, which agent-browser mistakes for a
    crash ("Chrome exited early without writing DevToolsActivePort"). The
    export therefore always drives an externally started browser. An
    already-working AGENT_BROWSER_CDP wins; otherwise a dedicated debug
    instance is started (or reused) on port 9337. The instance is left running
    on purpose: relaunching with the same profile joins the existing browser,
    so repeated exports reuse one instance instead of piling up processes.
    """
    if sys.platform != "win32":
        return None

    explicit = os.environ.get("AGENT_BROWSER_CDP")
    if explicit:
        try:
            if cdp_alive(int(explicit)):
                return int(explicit)
        except ValueError:
            pass
        log(f"AGENT_BROWSER_CDP={explicit} is not answering; starting a debug browser instead")

    port = DEBUG_CHROME_PORT
    if cdp_alive(port):
        return port
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            # Port taken by something that is not a CDP endpoint.
            with socket.socket() as spare:
                spare.bind(("127.0.0.1", 0))
                port = spare.getsockname()[1]

    executable = next((c for c in CHROME_CANDIDATES if Path(c).is_file()), None)
    if executable is None:
        raise ExportError(
            "no Chrome or Edge found to drive the export; install Google Chrome, "
            "or start a browser with --remote-debugging-port yourself and set "
            "AGENT_BROWSER_CDP to that port"
        )
    profile = task_tmp_dir() / "ansatz-slide-cdp-profile"
    log(f"starting debug browser on port {port}: {executable}")
    subprocess.Popen(
        [
            executable,
            f"--user-data-dir={profile}",
            f"--remote-debugging-port={port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-position=-2400,0",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if cdp_alive(port):
            return port
        time.sleep(0.5)
    raise ExportError(f"debug browser did not open CDP port {port} within 20s")


def find_manifest(source: Path) -> Path:
    source = source.expanduser().resolve()
    if source.is_file():
        if source.suffix.lower() != ".pptd":
            raise ExportError(f"input must be a .pptd file or project directory: {source}")
        return source
    if not source.is_dir():
        raise ExportError(f"input does not exist: {source}")
    manifests = sorted(source.rglob("*.pptd"))
    if not manifests:
        raise ExportError(f"no .pptd manifest found under: {source}")
    if len(manifests) > 1:
        choices = "\n  ".join(str(path) for path in manifests[:20])
        raise ExportError(
            "multiple .pptd manifests found; pass one manifest explicitly:\n  " + choices
        )
    return manifests[0]


def read_yaml_mapping(path: Path) -> Tuple[str, Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ExportError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ExportError(f"expected a YAML mapping in {path}")
    return text, value


def safe_project_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ExportError("page path must be a non-empty string")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ExportError(f"project path escapes the PPTD directory: {relative}") from exc
    return candidate


def build_image_map(root: Path) -> Dict[str, str]:
    image_map: Dict[str, str] = {}
    total = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_MIME:
            continue
        size = path.stat().st_size
        if size > MAX_IMAGE_BYTES:
            log(f"skip local image over 20 MiB: {path.relative_to(root)}")
            continue
        if total + size > MAX_EMBEDDED_MEDIA_BYTES:
            raise ExportError(
                "local image payload exceeds 200 MiB; reduce media size or use remote URLs"
            )
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        rel = path.relative_to(root).as_posix()
        image_map[rel] = f"data:{IMAGE_MIME[path.suffix.lower()]};base64,{data}"
        total += size
    if image_map:
        log(f"prepared {len(image_map)} local image resource(s), {total} bytes")
    return image_map


def build_payload(manifest: Path) -> Dict[str, Any]:
    manifest_text, manifest_data = read_yaml_mapping(manifest)
    if manifest_data.get("version") != "v2":
        raise ExportError("local PPTX export currently requires PPTD version: v2")
    page_paths = manifest_data.get("pages")
    if not isinstance(page_paths, list) or not page_paths:
        raise ExportError("PPTD manifest must contain a non-empty pages list")

    root = manifest.parent.resolve()
    pages: List[Dict[str, str]] = []
    page_documents: List[Dict[str, Any]] = []
    for entry in page_paths:
        page_path = safe_project_path(root, entry)
        if not page_path.is_file():
            raise ExportError(f"missing page file: {entry}")
        page_text, page_data = read_yaml_mapping(page_path)
        if not isinstance(page_data.get("elements"), list):
            raise ExportError(f"page elements must be an array: {entry}")
        pages.append({"path": str(entry), "content": page_text})
        page_documents.append({"path": str(entry).replace("\\", "/"), "data": page_data})

    run_strict_validator(
        {"manifest": manifest_data, "pages": page_documents},
        root,
    )

    title = str(manifest_data.get("title") or manifest.stem)
    return {
        "id": f"local-export-{uuid.uuid4().hex}",
        "title": title,
        "manifestPath": manifest.name,
        "manifestContent": manifest_text,
        "pages": pages,
        "imageMap": build_image_map(root),
    }


def run_strict_validator(document: Dict[str, Any], project_root: Path) -> None:
    """Reject semantically invalid PPTD before browser/WASM work begins.

    The Node exporter and the Python browser/image entry points share the same
    validator module. Keeping one executable rule set avoids accepting a
    document on one path and rejecting it on another.
    """
    if not VALIDATOR_MJS.is_file():
        raise ExportError(f"strict PPTD validator missing: {VALIDATOR_MJS}")
    node = shutil.which("node")
    if not node:
        raise ExportError("Node.js is required by the strict PPTD validator")
    try:
        encoded = json.dumps(
            {**document, "projectRoot": str(project_root)},
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ExportError(f"could not encode PPTD for strict validation: {exc}") from exc
    process = subprocess.run(
        [node, str(VALIDATOR_MJS), "--stdin"],
        input=encoded,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
    )
    if process.returncode != 0:
        raise ExportError(
            "strict PPTD validation failed:\n"
            f"{process.stdout[-12000:]}"
        )


def json_result(output: str) -> Dict[str, Any]:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ExportError(f"agent-browser returned no JSON object:\n{output[-2000:]}")


class BrowserSession:
    def __init__(
        self,
        executable: str,
        session: str,
        cwd: Path,
        download_dir: Path,
        cdp_port: Optional[int] = None,
    ):
        self.executable = executable
        self.session = session
        self.cwd = cwd
        # Kept as a search root fallback; not passed to agent-browser. On Windows,
        # --download-path can be rewritten to a \\?\ path that cancels Chrome downloads.
        self.download_dir = download_dir
        self.env = os.environ.copy()
        self.env.setdefault("AGENT_BROWSER_DEFAULT_TIMEOUT", "60000")
        self.env.setdefault("AGENT_BROWSER_IDLE_TIMEOUT_MS", "180000")
        # Local editor host is 127.0.0.1; corporate HTTP(S)_PROXY would otherwise
        # intercept and 403 the offline export page.
        for key in (
            "http_proxy",
            "https_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "all_proxy",
            "socks5_proxy",
            "SOCKS5_PROXY",
        ):
            self.env.pop(key, None)
        no_proxy = self.env.get("NO_PROXY") or self.env.get("no_proxy") or ""
        parts = {p.strip() for p in no_proxy.split(",") if p.strip()}
        parts.update({"127.0.0.1", "localhost", "::1"})
        joined = ",".join(sorted(parts))
        self.env["NO_PROXY"] = joined
        self.env["no_proxy"] = joined
        if cdp_port is not None:
            self.env["AGENT_BROWSER_CDP"] = str(cdp_port)

    def run(
        self,
        args: Sequence[str],
        *,
        timeout: int = 90,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = [self.executable, "--session", self.session, *args]
        process = run_command(command, cwd=self.cwd, env=self.env, timeout=timeout)
        if check and process.returncode != 0:
            raise ExportError(
                f"agent-browser command failed ({process.returncode}): "
                f"{' '.join(args)}\n{process.stdout[-4000:]}"
            )
        return process

    def open(self, url: str) -> None:
        # Avoid --download-path: agent-browser ≤0.33.2 + Chrome may cancel downloads
        # when given a verbatim Windows path. Files land in the default Downloads folder.
        self.run(["open", url], timeout=90)

    def snapshot(self) -> Dict[str, Any]:
        process = self.run(["snapshot", "-i", "-C", "--json"])
        return json_result(process.stdout)

    def close(self) -> None:
        self.run(["close"], timeout=20, check=False)


def snapshot_data(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    data = snapshot.get("data")
    if not isinstance(data, dict):
        raise ExportError(f"invalid agent-browser snapshot: {snapshot}")
    return data


def ref_by_name(snapshot: Dict[str, Any], name: str, role: Optional[str] = None) -> str:
    refs = snapshot_data(snapshot).get("refs")
    if not isinstance(refs, dict):
        raise ExportError("snapshot contains no interactive refs")
    matches = []
    for ref, metadata in refs.items():
        if not isinstance(metadata, dict) or metadata.get("name") != name:
            continue
        if role is not None and str(metadata.get("role", "")).lower() != role.lower():
            continue
        matches.append(ref)
    if not matches:
        raise ExportError(f"could not find {role or 'element'} named {name!r}")
    return matches[-1]


def switch_state(snapshot: Dict[str, Any]) -> Optional[Tuple[str, bool, bool]]:
    text = str(snapshot_data(snapshot).get("snapshot") or "")
    match = re.search(r"switch \[(?P<attrs>[^\]]*?)ref=(?P<ref>e\d+)\]", text)
    if not match:
        return None
    attrs = match.group("attrs")
    return match.group("ref"), "checked=true" in attrs, "disabled" in attrs


def wait_for_export_dialog(browser: BrowserSession, timeout: float = 20.0) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: Optional[Dict[str, Any]] = None
    while time.monotonic() < deadline:
        last = browser.snapshot()
        try:
            ref_by_name(last, "下载", "button")
            return last
        except ExportError:
            time.sleep(0.35)
    raise ExportError(f"export dialog did not become ready: {last}")


def is_pptx(path: Path) -> bool:
    if not path.is_file() or path.name.endswith(".crdownload"):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            if "ppt/presentation.xml" not in archive.namelist():
                return False
            content_types = archive.read("[Content_Types].xml")
            return PPTX_CONTENT_TYPE.encode("utf-8") in content_types
    except (OSError, KeyError, zipfile.BadZipFile):
        return False


def find_download(
    search_roots: Iterable[Path],
    timeout: float = 150.0,
    accept: Callable[[Path], bool] = is_pptx,
    *,
    since: Optional[float] = None,
) -> Path:
    deadline = time.monotonic() + timeout
    last_sizes: Dict[Path, int] = {}
    stable: Dict[Path, int] = {}
    while time.monotonic() < deadline:
        # Snapshot stats while collecting and tolerate races everywhere: the
        # search roots include the live Downloads folder, where Chrome renames
        # .crdownload files away between directory listing and stat().
        entries: List[Tuple[Path, float, int]] = []
        for root in search_roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    info = path.stat()
                except OSError:
                    continue
                entries.append((path, info.st_mtime, info.st_size))
        for path, mtime, size in sorted(entries, key=lambda entry: entry[1], reverse=True):
            if since is not None and mtime < since:
                continue
            if size == last_sizes.get(path) and size > 0:
                stable[path] = stable.get(path, 0) + 1
            else:
                stable[path] = 0
            last_sizes[path] = size
            if stable[path] >= 1 and accept(path):
                return path
        time.sleep(0.5)
    visible = "\n  ".join(str(path) for path in last_sizes) or "(none)"
    raise ExportError(f"timed out waiting for download; observed files:\n  {visible}")


def replace_transition(slide_xml: bytes, transition: str) -> bytes:
    text = slide_xml.decode("utf-8")
    pattern = re.compile(
        r"<p:transition\b[^>]*(?:/>|>.*?</p:transition>)", re.DOTALL
    )
    text = pattern.sub("", text)
    if transition == "none":
        return text.encode("utf-8")

    # CT_Slide requires transition as a direct child after cSld/clrMapOvr and
    # before timing/extLst. Searching for the first p:extLst is incorrect:
    # shapes may contain their own nested extLst inside cSld, causing Office to
    # ignore a transition inserted there.
    color_map = re.search(
        r"<p:clrMapOvr\b[^>]*(?:/>|>.*?</p:clrMapOvr>)", text, re.DOTALL
    )
    common_slide = re.search(
        r"<p:cSld\b[^>]*(?:/>|>.*?</p:cSld>)", text, re.DOTALL
    )
    anchor = color_map or common_slide
    if anchor is None:
        raise ExportError("slide XML has no cSld/clrMapOvr insertion anchor")
    position = anchor.end()
    return (text[:position] + FADE_TRANSITION_XML + text[position:]).encode("utf-8")


def root_child_names(slide_xml: bytes) -> List[str]:
    try:
        root = ET.fromstring(slide_xml)
    except ET.ParseError as exc:
        raise ExportError(f"invalid slide XML: {exc}") from exc
    return [child.tag.rsplit("}", 1)[-1] for child in root]


def has_direct_fade_transition(slide_xml: bytes) -> bool:
    try:
        root = ET.fromstring(slide_xml)
    except ET.ParseError as exc:
        raise ExportError(f"invalid slide XML: {exc}") from exc
    transition = next(
        (child for child in root if child.tag.rsplit("}", 1)[-1] == "transition"),
        None,
    )
    if transition is None:
        return False
    return any(child.tag.rsplit("}", 1)[-1] == "fade" for child in transition)


def validate_transition_order(slide_xml: bytes, transition: str) -> None:
    names = root_child_names(slide_xml)
    transition_indexes = [index for index, name in enumerate(names) if name == "transition"]
    if transition == "none":
        if transition_indexes:
            raise ExportError("transition=none left a root-level transition")
        return
    if len(transition_indexes) != 1 or not has_direct_fade_transition(slide_xml):
        raise ExportError("slide does not contain exactly one root-level fade transition")
    transition_index = transition_indexes[0]
    for required_before in ("cSld", "clrMapOvr"):
        if required_before in names and names.index(required_before) > transition_index:
            raise ExportError(f"{required_before} appears after transition")
    for required_after in ("timing", "extLst"):
        if required_after in names and names.index(required_after) < transition_index:
            raise ExportError(f"{required_after} appears before transition")


def patch_transitions(pptx: Path, transition: str) -> int:
    temporary = pptx.with_name(f".{pptx.name}.{uuid.uuid4().hex}.tmp")
    slide_count = 0
    try:
        with zipfile.ZipFile(pptx, "r") as source, zipfile.ZipFile(temporary, "w") as target:
            target.comment = source.comment
            for info in source.infolist():
                data = source.read(info.filename)
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", info.filename):
                    data = replace_transition(data, transition)
                    slide_count += 1
                target.writestr(info, data, compress_type=info.compress_type)
        if slide_count == 0:
            raise ExportError("exported PPTX contains no slide XML")
        temporary.replace(pptx)
    finally:
        temporary.unlink(missing_ok=True)
    return slide_count


def verify_output(pptx: Path, transition: str, expect_fonts: bool) -> Dict[str, Any]:
    if not is_pptx(pptx):
        raise ExportError(f"output is not a valid PPTX ZIP: {pptx}")
    with zipfile.ZipFile(pptx) as archive:
        broken = archive.testzip()
        if broken:
            raise ExportError(f"PPTX CRC check failed at: {broken}")
        slide_names = [
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        ]
        slide_xml = {name: archive.read(name) for name in slide_names}
        for data in slide_xml.values():
            validate_transition_order(data, transition)
        transition_hits = sum(has_direct_fade_transition(data) for data in slide_xml.values())
        if transition == "fade" and transition_hits != len(slide_names):
            raise ExportError("fade transition was not written to every slide")
        fonts = [
            name
            for name in archive.namelist()
            if name.startswith("ppt/fonts/") and not name.endswith("/")
        ]
        if expect_fonts and not fonts:
            log(
                "warning: embed-fonts was enabled, but the official writer produced no font part"
            )
        return {
            "slides": len(slide_names),
            "fadeTransitions": transition_hits,
            "fontParts": len(fonts),
            "bytes": pptx.stat().st_size,
        }


def resolve_editor_root() -> Path:
    """Locate the offline neo-ppt mirror (package editor/ or skill-installed copy)."""
    env = os.environ.get("ANSATZ_SLIDE_EDITOR")
    candidates: List[Path] = []
    if env:
        candidates.append(Path(env).expanduser().resolve())
    candidates.append(SKILL_DIR / "editor")
    # monorepo / npm package: skills/ansatz-slide → package root
    candidates.append(SKILL_DIR.parent.parent / "editor")
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    raise ExportError(EDITOR_MISSING_HINT)


def serve(
    directory: Path,
    *,
    entry: str = "index.html",
) -> Tuple[ThreadingHTTPServer, threading.Thread, str]:
    """Legacy static serve (tests / callers). Prefer serve_local_editor for exports."""
    handler = lambda *args, **kwargs: QuietHandler(  # noqa: E731
        *args, directory=str(directory), **kwargs
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, f"http://{host}:{port}/{entry.lstrip('/')}"


def serve_local_editor(
    payload: Dict[str, Any],
) -> Tuple[ThreadingHTTPServer, threading.Thread, str]:
    """Serve the offline editor and inject payload.json for headless export."""
    editor_root = resolve_editor_root()
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    class LocalEditorHandler(QuietHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(editor_root), **kwargs)

        def _is_payload(self) -> bool:
            path = urlparse(self.path).path
            return path in ("/payload.json", "payload.json")

        def do_GET(self) -> None:  # noqa: N802
            if self._is_payload():
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(payload_bytes)
                return
            return SimpleHTTPRequestHandler.do_GET(self)

        def do_HEAD(self) -> None:  # noqa: N802
            if self._is_payload():
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            return SimpleHTTPRequestHandler.do_HEAD(self)

    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalEditorHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    url = f"http://{host}:{port}/?ndExport=1"
    log(f"local editor host: {url} (root={editor_root})")
    return server, thread, url


LOCAL_EXPORT_DIR = Path(__file__).resolve().parent / "local-export"
LOCAL_EXPORT_MJS = LOCAL_EXPORT_DIR / "export-pptd.mjs"
VALIDATOR_MJS = LOCAL_EXPORT_DIR / "validate-pptd.mjs"
# Canonical patched WASM: editor/neo-ppt/assets/ (repo/npm). Skill install copies it
# into local-export/pptd_wasm_bg.wasm for ~/.agents|~/.claude skills trees.
CANONICAL_WASM_NAME = "pptd_wasm_bg-DPPWdROu.wasm"


def resolve_local_wasm() -> Path:
    package_root = Path(__file__).resolve().parents[3]
    candidates = [
        LOCAL_EXPORT_DIR / "pptd_wasm_bg.wasm",
        LOCAL_EXPORT_DIR / CANONICAL_WASM_NAME,
        SKILL_DIR / "editor" / "neo-ppt" / "assets" / CANONICAL_WASM_NAME,
        package_root / "editor" / "neo-ppt" / "assets" / CANONICAL_WASM_NAME,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ExportError(
        "patched WASM not found. Expected "
        f"editor/neo-ppt/assets/{CANONICAL_WASM_NAME} (repo/npm package) or "
        f"{LOCAL_EXPORT_DIR / 'pptd_wasm_bg.wasm'} (after skill install)."
    )


def export_pptx_local(
    source: Path,
    output: Path,
    transition: str,
    force: bool = False,
) -> Dict[str, Any]:
    """Export via local patched official WASM (no cookie / no browser UI)."""
    if not LOCAL_EXPORT_MJS.is_file():
        raise ExportError(f"local exporter missing: {LOCAL_EXPORT_MJS}")
    wasm_path = resolve_local_wasm()
    node = shutil.which("node")
    if not node:
        raise ExportError("node is required for local WASM export")

    manifest = find_manifest(source)
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not force:
        raise ExportError(f"output already exists (pass --force to replace it): {output}")

    log(f"local WASM export: {manifest} → {output}")
    log(f"defaults: transition={transition} (no-sign / signature bypassed)")

    # Pass project directory so media paths resolve relative to the deck root.
    project_dir = manifest.parent if manifest.is_file() else source
    cmd = [
        node,
        str(LOCAL_EXPORT_MJS),
        str(project_dir),
        "-o",
        str(output),
        "--no-sign",
        "--transition",
        transition if transition in ("fade", "none") else "fade",
        "--wasm",
        str(wasm_path),
    ]

    process = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
    )
    if process.returncode != 0:
        raise ExportError(
            f"local WASM export failed ({process.returncode}):\n{process.stdout[-4000:]}"
        )

    slide_count = patch_transitions(output, transition)
    summary = verify_output(output, transition, expect_fonts=False)
    summary["transitionPatchedSlides"] = slide_count
    summary["output"] = str(output)
    summary["exporter"] = "local-wasm-patched"
    log(f"local export ok: {output} ({output.stat().st_size} bytes)")
    return summary


def export_pptx(
    source: Path,
    output: Path,
    transition: str,
    embed_fonts: bool,
    keep_download: bool = False,
    force: bool = False,
    prefer_local: bool = True,
) -> Dict[str, Any]:
    """Prefer local patched WASM; fall back to local neo-ppt browser UI."""
    if prefer_local:
        try:
            return export_pptx_local(source, output, transition, force=force)
        except ExportError as exc:
            log(f"local WASM export unavailable ({exc}); falling back to local browser editor")

    manifest = find_manifest(source)
    payload = build_payload(manifest)
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not force:
        raise ExportError(f"output already exists (pass --force to replace it): {output}")
    agent_browser = ensure_agent_browser()
    cdp_port = ensure_debug_chrome()

    log(f"manifest: {manifest}")
    log(
        f"defaults: transition={transition}, embed_fonts={'on' if embed_fonts else 'off'}"
    )

    with temporary_directory(prefix="ansatz-slide-export-") as temp_name:
        temp_dir = Path(temp_name)
        download_dir = temp_dir / "downloads"
        download_dir.mkdir()
        server, thread, url = serve_local_editor(payload)
        session = f"ansatz-slide-export-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        browser = BrowserSession(agent_browser, session, temp_dir, download_dir, cdp_port)
        downloads = default_downloads_dir()
        try:
            log("opening the local neo-ppt editor")
            browser.open(url)
            browser.run(
                [
                    "wait",
                    "--fn",
                    'document.documentElement.dataset.deckStatus === "ready"',
                ],
                timeout=120,
            )
            browser.run(["set", "viewport", "1280", "720"])
            snapshot = browser.snapshot()
            export_ref = ref_by_name(snapshot, "导出", "button")
            browser.run(["click", f"@{export_ref}"])
            dialog = wait_for_export_dialog(browser)

            state = switch_state(dialog)
            if state is not None:
                switch_ref, checked, disabled = state
                if disabled and checked != embed_fonts:
                    log("warning: the font switch is disabled for this deck")
                elif checked != embed_fonts:
                    browser.run(["click", f"@{switch_ref}"])
                    dialog = wait_for_export_dialog(browser)
            elif embed_fonts:
                log("warning: the export dialog exposed no font switch")

            # Plain click (not agent-browser `download`) so Chrome saves to the
            # default Downloads folder; --download-path is broken on some Windows setups.
            started_at = time.time() - 1.0
            download_ref = ref_by_name(dialog, "下载", "button")
            log("generating PPTX in the local editor")
            browser.run(["click", f"@{download_ref}"], timeout=180)
            downloaded = find_download(
                (downloads, download_dir, temp_dir),
                timeout=90,
                since=started_at,
            )
            shutil.copy2(downloaded, output)
            if keep_download:
                debug_copy = output.with_name(f"{output.stem}.browser-raw.pptx")
                if debug_copy.exists() and not force:
                    raise ExportError(
                        f"raw debug output already exists (pass --force): {debug_copy}"
                    )
                shutil.copy2(downloaded, debug_copy)
            try:
                if downloaded.resolve().parent == downloads.resolve():
                    downloaded.unlink(missing_ok=True)
            except OSError:
                pass
        finally:
            browser.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    slide_count = patch_transitions(output, transition)
    summary = verify_output(output, transition, embed_fonts)
    summary["transitionPatchedSlides"] = slide_count
    summary["output"] = str(output)
    summary["exporter"] = "browser-local-editor"
    return summary


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export a PPTD project to PPTX. "
            "Default: local patched official WASM (offline). "
            "Optional --browser uses the local neo-ppt mirror (also offline)."
        )
    )
    parser.add_argument("input", type=Path, help=".pptd manifest or project directory")
    parser.add_argument("--output", "-o", type=Path, help="output .pptx path")
    parser.add_argument(
        "--transition",
        choices=("fade", "none"),
        default="fade",
        help="slide transition written to every slide (default: fade)",
    )
    font_group = parser.add_mutually_exclusive_group()
    font_group.add_argument(
        "--embed-fonts",
        dest="embed_fonts",
        action="store_true",
        default=False,
        help="request font embedding when available (browser path only; off by default)",
    )
    font_group.add_argument(
        "--no-embed-fonts",
        dest="embed_fonts",
        action="store_false",
        help="disable font embedding (browser path)",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="force local neo-ppt browser UI path instead of Node WASM",
    )
    parser.add_argument(
        "--keep-browser-raw",
        action="store_true",
        help="also keep the unpatched browser download beside the output",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing output file",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        manifest = find_manifest(args.input)
        output = args.output or manifest.with_suffix(".pptx")
        summary = export_pptx(
            args.input,
            output,
            args.transition,
            args.embed_fonts,
            args.keep_browser_raw,
            args.force,
            prefer_local=not args.browser,
        )
    except (ExportError, OSError, subprocess.SubprocessError) as exc:
        print(f"ansatz-slide export failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
