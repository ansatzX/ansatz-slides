"""Install a self-contained Python skill without Node or browser resources."""

import shutil
import tempfile
from pathlib import Path

_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".DS_Store", "_user_meta.json", "tests", "local-export"
)


def install_skill(target, *, force=False):
    target = Path(target).expanduser().resolve()
    package = Path(__file__).resolve().parent
    source = package / "skill"
    if not (source / "SKILL.md").is_file():
        source = package.parents[1] / "skills" / "ansatz-slide"
    if not (source / "SKILL.md").is_file():
        raise FileNotFoundError("Skill instructions are missing from this installation")
    destination = target / "ansatz-slide"
    if (destination.exists() or destination.is_symlink()) and not force:
        raise FileExistsError(f"{destination} exists; use --force to replace it")
    # Never replace a directory containing the executing package or skill source.
    for path in (source, package):
        if path.is_relative_to(
            destination.resolve()
        ) or destination.resolve().is_relative_to(path):
            raise ValueError("Installation target overlaps the running source")
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ansatz-slide-", dir=target) as staging:
        staged = Path(staging) / "new"
        shutil.copytree(source, staged, ignore=_IGNORE)
        shutil.copytree(
            package,
            staged / "python" / "ansatz_slide",
            ignore=shutil.ignore_patterns("skill", "__pycache__", "*.pyc"),
        )
        # A standalone skill is a dependency-only project, not a wheel checkout.
        (staged / "pyproject.toml").write_text(
            """[project]
name = "ansatz-slide-skill"
version = "0.0.1"
requires-python = ">=3.11"
dependencies = ["PyYAML==6.0.3"]
[tool.uv]
package = false
""",
            encoding="utf-8",
        )
        lock = source / "runtime.lock"
        if lock.is_file():
            shutil.copy2(lock, staged / "uv.lock")
            (staged / "runtime.lock").unlink()
        backup = Path(staging) / "previous"
        if destination.exists() or destination.is_symlink():
            destination.rename(backup)
        try:
            staged.rename(destination)
        except BaseException:
            if backup.exists() or backup.is_symlink():
                backup.rename(destination)
            raise
    return {
        "ok": True,
        "destination": str(destination),
        "runtime": "Python",
        "version": "0.0.1",
    }
