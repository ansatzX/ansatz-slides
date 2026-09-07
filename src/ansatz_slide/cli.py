"""One Python CLI for validation, export, single-page replacement and inspection."""

import argparse
import json
import sys
from pathlib import Path

from .inspection import inspect_pptx
from .project import export_project, load_project


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ansatz-slide", description=__doc__)
    parser.add_argument("--version", action="version", version="ansatz-slide 0.0.1")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate a YAML presentation project")
    validate.add_argument("source")
    export = commands.add_parser("export", help="Export YAML sources to editable PPTX")
    export.add_argument("source")
    export.add_argument("-o", "--output", required=True)
    export.add_argument("--transition", choices=("fade", "none"), default="fade")
    export.add_argument("--force", action="store_true")
    export.add_argument(
        "--offline", action="store_true", help="Reject HTTP image resources"
    )
    check = commands.add_parser(
        "inspect", help="Check actual PPTX package/relationships (not visual quality)"
    )
    check.add_argument("source")
    replace = commands.add_parser(
        "replace-page",
        help="Export candidate and replace one page, preserving other pages",
    )
    replace.add_argument("--baseline", required=True, type=Path)
    replace.add_argument("--project", required=True, type=Path)
    replace.add_argument("--page", required=True, type=int)
    replace.add_argument("-o", "--output", required=True, type=Path)
    replace.add_argument("--transition", choices=("fade", "none"), default="fade")
    replace.add_argument("--force", action="store_true")
    replace.add_argument("--offline", action="store_true")
    install = commands.add_parser("install-skill", help="Install the standalone Python skill")
    install.add_argument("--target", required=True, type=Path, help="Parent directory containing skills")
    install.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "install-skill":
            from .installation import install_skill
            result = install_skill(args.target, force=args.force)
        elif args.command == "validate":
            pptd, _ = load_project(args.source)
            result = {"ok": True, "pageCount": len(pptd["pages"])}
        elif args.command == "export":
            result = export_project(
                args.source,
                args.output,
                transition=args.transition,
                force=args.force,
                allow_remote=not args.offline,
            )
        elif args.command == "inspect":
            result = inspect_pptx(args.source)
        else:
            from .incremental import replace_from_project

            result = replace_from_project(
                args.baseline,
                args.project,
                args.page,
                args.output,
                transition=args.transition,
                force=args.force,
                allow_remote=not args.offline,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
