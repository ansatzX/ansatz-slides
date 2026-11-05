"""统一 CLI 参数声明；命令执行在 cli.main 中分派。"""

import argparse
from pathlib import Path


def build_parser(description):
    parser = argparse.ArgumentParser(prog="ansatz-slide", description=description)
    parser.add_argument("--version", action="version", version="ansatz-slide 0.0.1")
    detail = parser.add_mutually_exclusive_group()
    detail.add_argument(
        "--compact", action="store_true", help="Compact work evidence (default)"
    )
    detail.add_argument(
        "--full",
        action="store_true",
        help="Include full work evidence on stdout; does not generate matrices",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser(
        "validate", help="Validate a YAML presentation project"
    )
    validate.add_argument("source")
    export = commands.add_parser("export", help="Export YAML sources to editable PPTX")
    export.add_argument("source")
    export.add_argument("--backend", choices=("native", "deckcraft"), default="native")
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
    install = commands.add_parser(
        "install-skill", help="Install the standalone Python skill"
    )
    install.add_argument(
        "--target", required=True, type=Path, help="Parent directory containing skills"
    )
    install.add_argument("--force", action="store_true")
    page = commands.add_parser(
        "page", help="Inspect and edit one source page at a time"
    )
    page_actions = page.add_subparsers(dest="page_action", required=True)
    open_page = page_actions.add_parser(
        "open",
        help="Open a page work object with candidate, geometry issues and preview",
    )
    open_page.add_argument("project", type=Path)
    open_page.add_argument(
        "--page",
        required=True,
        type=int,
        action="append",
        help="Repeat to open several independent pages in one call",
    )
    open_page.add_argument(
        "--no-preview",
        action="store_true",
        help="Read for editing without rendering the old page; update still renders and validates",
    )
    open_page.add_argument("--width", type=int, default=1600)
    update_page = page_actions.add_parser(
        "update",
        help="Update or retry the retained candidate in a revision-bound work object",
    )
    update_page.add_argument("work", type=Path)
    update_page.add_argument("--content", type=Path)
    update_page.add_argument("--element")
    update_page.add_argument("--changes", type=Path)
    update_page.add_argument(
        "--allow-duplicates",
        action="store_true",
        help="Explicitly permit a retained duplicate insertion",
    )
    update_page.add_argument("--candidate", type=int, default=1)
    update_page.add_argument(
        "--edits",
        type=Path,
        help="List of element/changes patches applied as one checked page revision",
    )
    update_page.add_argument(
        "--layout",
        type=Path,
        help="Deterministic row/column/group/weighted-segment layout of existing elements",
    )
    for name in ("resume", "rebase"):
        recovery = page_actions.add_parser(
            name, help="Recover the latest retained work without publishing"
        )
        recovery.add_argument("work", type=Path)
        if name == "rebase":
            recovery.add_argument("--page", type=int)
    check_page = page_actions.add_parser(
        "check", help="Expose one page, its rendered preview and bounded context"
    )
    check_page.add_argument("--project", required=True, type=Path)
    check_page.add_argument("--page", required=True, type=int)
    check_page.add_argument("--session", required=True, type=Path)
    check_page.add_argument("--width", type=int, default=1600)
    geometry = page_actions.add_parser(
        "check-overlap",
        help="Generate occupancy matrices and grayscale bounds maps without an Office renderer",
    )
    geometry.add_argument("--project", type=Path, required=True)
    geometry.add_argument("--page", type=int, required=True)
    geometry.add_argument(
        "--output", type=Path, required=True, help="New output directory"
    )
    geometry.add_argument(
        "--cell-size", type=float, default=1, help="Canvas units per matrix cell"
    )
    edit_page = page_actions.add_parser(
        "edit", help="Replace only the page pinned by check; return its new preview"
    )
    edit_page.add_argument("session", type=Path)
    edit_page.add_argument("--token", required=True)
    edit_page.add_argument(
        "--content",
        type=Path,
        help="One .page.yaml object; default is the session's editable page",
    )
    split = page_actions.add_parser(
        "split", help="Replace one checked page with multiple pages in manifest order"
    )
    split.add_argument("session", type=Path)
    split.add_argument("--token", help="Legacy session token")
    split.add_argument("--content", action="append", type=Path, required=True)
    merge = page_actions.add_parser(
        "merge", help="Merge two separately checked adjacent pages"
    )
    merge.add_argument("session", type=Path)
    merge.add_argument("--token", help="Legacy session token")
    merge.add_argument("--next-session", type=Path)
    merge.add_argument("--next", type=Path, help="Adjacent page work reference")
    merge.add_argument("--next-token")
    merge.add_argument("--content", type=Path, required=True)
    patch = page_actions.add_parser(
        "patch",
        help="Update fields of one element by ID and return a fresh page preview",
    )
    patch.add_argument("session", type=Path)
    patch.add_argument("--token", required=True)
    patch.add_argument("--element", required=True)
    patch.add_argument(
        "--changes",
        type=Path,
        required=True,
        help="JSON/YAML object of element fields; nested maps merge, arrays replace",
    )
    for name in ("insert", "move", "remove"):
        action = page_actions.add_parser(
            name,
            help=f"{name.capitalize()} one page in manifest order; retain existing source files",
        )
        action.add_argument("session", type=Path)
        action.add_argument("--token", help="Legacy session token")
        if name != "remove":
            action.add_argument(
                "--position", choices=("before", "after"), default="after"
            )
        if name == "insert":
            action.add_argument("--content", type=Path, required=True)
            action.add_argument("--allow-duplicates", action="store_true")
        if name == "move":
            action.add_argument("--anchor-session", type=Path)
            action.add_argument(
                "--anchor", type=Path, help="Anchor page work reference"
            )
            action.add_argument("--anchor-token")
    text_check = page_actions.add_parser(
        "check-text", help="Measure native text with actual fonts and line layout"
    )
    text_check.add_argument("--project", required=True, type=Path)
    text_check.add_argument("--page", required=True, type=int)
    text_check.add_argument("--output", required=True, type=Path)
    deck = commands.add_parser(
        "deck", help="Read the outline or publish a checked draft manifest"
    )
    deck_actions = deck.add_subparsers(dest="deck_action", required=True)
    preflight = deck_actions.add_parser(
        "preflight",
        help="Check sources before PPTX/Office work; never render, fetch assets or publish",
    )
    preflight.add_argument(
        "source", type=Path, help="Existing project or future project asset root"
    )
    preflight.add_argument(
        "--plan", type=Path, help="Candidate page list, in import-pages format"
    )
    preflight.add_argument(
        "--settings",
        type=Path,
        help="Creation settings without pages, required with --plan",
    )
    preflight.add_argument("--page", type=int, action="append")
    preflight.add_argument("--offline", action="store_true")
    preflight.add_argument(
        "--strict",
        action="store_true",
        help="Return nonzero for advisory findings as well as errors",
    )
    preflight.add_argument(
        "--basic",
        action="store_true",
        help="Only schema, geometry and local asset checks; skip academic hints",
    )
    batch = deck_actions.add_parser(
        "import-pages",
        help="Create/insert an ordered batch with idempotency and retained candidates",
    )
    batch.add_argument("project", type=Path)
    batch.add_argument("--plan", type=Path, required=True)
    batch.add_argument("--request-id", required=True)
    batch.add_argument("--settings", type=Path)
    batch.add_argument("--after", type=int)
    batch.add_argument("--allow-duplicates", action="store_true")
    batch.add_argument("--width", type=int, default=1600)
    resume_deck = deck_actions.add_parser(
        "resume", help="Resume a retained batch; applied requests never insert twice"
    )
    resume_deck.add_argument("token", type=Path)
    check_deck = deck_actions.add_parser("check")
    check_deck.add_argument("--project", required=True, type=Path)
    create_deck = deck_actions.add_parser(
        "create",
        help="Precheck every draft page before creating the formal pptx.yaml manifest",
    )
    create_deck.add_argument("project", nargs="?", type=Path)
    create_deck.add_argument("--settings", type=Path)
    create_deck.add_argument("--content", type=Path, help="First page candidate")
    create_deck.add_argument(
        "--draft", type=Path, help="Legacy draft manifest publication"
    )
    create_deck.add_argument("--output", type=Path)
    outline_deck = deck_actions.add_parser(
        "outline",
        help="Read or record model-authored purpose, claim, evidence and connection",
    )
    outline_deck.add_argument("project", type=Path)
    outline_deck.add_argument("--page", type=int)
    outline_deck.add_argument("--content", type=Path)
    for name in ("brief", "directive"):
        action = deck_actions.add_parser(
            name, help="Read or record deck argument and attributed directives"
        )
        action.add_argument("project", type=Path)
        action.add_argument("--content", type=Path)
        action.add_argument("--history", action="store_true")
        if name == "directive":
            action.add_argument(
                "--revoke", help="Revoke one directive ID, preserving history"
            )
            action.add_argument(
                "--source", help="Reference for the revocation instruction"
            )
            action.add_argument(
                "--quote", help="Exact relevant text from the revocation instruction"
            )
    export_deck = deck_actions.add_parser(
        "export", help="Export current checked sources"
    )
    export_deck.add_argument("source", type=Path)
    export_deck.add_argument(
        "--backend", choices=("native", "deckcraft"), default="native"
    )
    export_deck.add_argument("-o", "--output", type=Path, required=True)
    export_deck.add_argument("--force", action="store_true")
    export_deck.add_argument("--offline", action="store_true")
    export_deck.add_argument("--transition", choices=("none", "fade"), default="none")
    open_deck = deck_actions.add_parser(
        "open", help="Read selected pages and create one version-bound edit plan"
    )
    open_deck.add_argument("project", type=Path)
    open_deck.add_argument("--page", type=int, action="append")
    open_deck.add_argument("--width", type=int, default=1600)
    open_deck.add_argument("--no-preview", action="store_true")
    review_deck = deck_actions.add_parser(
        "review",
        help="Record a human/Agent visual observation for an unchanged rendered version",
    )
    review_deck.add_argument("directory", type=Path)
    review_deck.add_argument("--page", type=int, required=True)
    review_deck.add_argument(
        "--status", choices=("reviewed", "needs_fix"), required=True
    )
    review_deck.add_argument("--note", required=True)
    revise_deck = deck_actions.add_parser(
        "revise",
        help="Apply a version-bound page plan, export once and render final previews",
    )
    revise_deck.add_argument("project", type=Path)
    revise_deck.add_argument("--plan", type=Path, required=True)
    revise_deck.add_argument("-o", "--output", type=Path, required=True)
    revise_deck.add_argument("--force", action="store_true")
    revise_deck.add_argument("--width", type=int, default=1600)
    return parser
