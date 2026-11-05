"""页面级快照、预览和可恢复的源文件发布。

本 API 将编辑会话绑定到页面与源文件哈希，校验并预览候选稿后，只发布目标
页面或清单顺序变更。令牌用于发现过期输入，但不能阻止外部写入，因此发布
前后还会复查哈希，并保留备份以便回滚。
"""

import hashlib
import html
import json
import os
import re
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path

from ..project import (
    find_manifest,
    image_objects,
    parse_document,
)
from ..validation import safe_path, validate_project


def sha(data):
    return hashlib.sha256(data).hexdigest()


def page_fingerprint(page):
    """Structural page identity independent of JSON/YAML mapping key order."""
    return sha(
        json.dumps(
            page, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def session_path(value):
    path = Path(value).absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("Session path must not contain symlinks")
    if path.exists():
        if not path.is_dir():
            raise ValueError("Session must be a directory")
        for base, dirs, files in os.walk(path, followlinks=False):
            for name in dirs + files:
                item = Path(base) / name
                mode = item.lstat().st_mode
                if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                    raise ValueError(
                        f"Session artifacts must not be symlinks or special files: {item}"
                    )
    return path


def session_write(session, name, data):
    session_path(session)
    # Bind writes to the opened directory; replace the final name, never resolve
    # it through a symlink. Only fixed immediate-child artifact names are allowed.
    if name not in ("page.page.yaml", "session.json"):
        raise ValueError("Unknown session artifact")
    fd = os.open(
        session,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary = ".write-" + uuid.uuid4().hex
    try:
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=fd)
        with os.fdopen(out, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass
        os.close(fd)


@contextmanager
def lock(path):
    """Kernel-owned lock; keep the inode stable so process death releases ownership."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Lock must be a regular file")
        if os.name == "nt":
            import msvcrt

            if os.fstat(fd).st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError(
                    f"Another edit/check owns {path}; retry after it finishes"
                ) from exc
        else:
            import fcntl

            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError(
                    f"Another edit/check owns {path}; retry after it finishes"
                ) from exc
        yield
    finally:
        # Do not unlink: waiters and new arrivals must lock the same inode.
        os.close(fd)


def snapshot(project):
    """读取项目并记录清单、页面及素材的哈希快照。"""
    manifest_path = find_manifest(project)
    root = manifest_path.parent
    manifest_data = manifest_path.read_bytes()
    manifest = parse_document(manifest_data.decode("utf-8"), str(manifest_path))
    pages, paths = [], []
    tracked = {str(manifest_path): sha(manifest_data)}
    for rel in manifest.get("pages", []):
        path = safe_path(root, rel, "page")
        if not path.name.lower().endswith(".page.yaml"):
            raise ValueError("Page source must use .page.yaml")
        if path in paths:
            raise ValueError(
                "Single-page editing requires distinct page source paths; this manifest reuses a page file"
            )
        paths.append(path)
        data = path.read_bytes()
        tracked[str(path)] = sha(data)
        pages.append(parse_document(data.decode("utf-8"), str(path)))
    validate_project(manifest, pages, root)
    for image in image_objects({"manifest": manifest, "pages": pages}):
        src = image["src"]
        if not re.match(r"(?i)^(data:|https?://)", src):
            path = safe_path(root, src, "image")
            tracked[str(path)] = sha(path.read_bytes())
    return {
        "manifestPath": manifest_path,
        "root": root,
        "manifest": manifest,
        "pages": pages,
        "paths": paths,
        "tracked": tracked,
    }


def unchanged(tracked):
    return all(
        Path(p).is_file() and sha(Path(p).read_bytes()) == value
        for p, value in tracked.items()
    )


def page_token(snap, number):
    path = snap["paths"][number - 1]
    tracked = {
        str(snap["manifestPath"]): snap["tracked"][str(snap["manifestPath"])],
        str(path): snap["tracked"][str(path)],
    }
    for image in image_objects(
        {"manifest": snap["manifest"], "page": snap["pages"][number - 1]}
    ):
        if not re.match(r"(?i)^(data:|https?://)", image["src"]):
            p = safe_path(snap["root"], image["src"], "image")
            tracked[str(p)] = snap["tracked"][str(p)]
    return sha(json_bytes([number, tracked]))


def presentation_token(snap, number):
    page = snap["pages"][number - 1]
    tracked = {
        str(snap["paths"][number - 1]): snap["tracked"][str(snap["paths"][number - 1])]
    }
    for image in image_objects({"manifest": snap["manifest"], "page": page}):
        if not re.match(r"(?i)^(data:|https?://)", image["src"]):
            path = safe_path(snap["root"], image["src"], "image")
            tracked[str(path)] = snap["tracked"][str(path)]
    appearance = {
        key: snap["manifest"].get(key) for key in ("size", "theme", "customFonts")
    }
    return sha(json_bytes([tracked, appearance]))


def title(page):
    candidates = []
    for element in page.get("elements", []):
        content = element.get("content", {})
        if element.get("elementType") == "text" and isinstance(content, dict):
            text = html.unescape(re.sub("<[^>]*>", "", content.get("text", ""))).strip()
            if text:
                priority = (
                    10000
                    if element.get("elementId", "").lower() in ("title", "heading")
                    else 0
                )
                candidates.append((priority + content.get("fontSize", 0), text))
    return max(candidates, default=(0, ""), key=lambda v: v[0])[1]


def context(snap, number):
    return [
        {"page": i + 1, "title": title(p)}
        for i, p in enumerate(snap["pages"])
        if abs(i + 1 - number) == 1
    ]
