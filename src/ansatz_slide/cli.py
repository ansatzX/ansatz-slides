"""One Python CLI for validation, export, single-page replacement, inspection and page review."""

# 各命令分支调用所属模块的 API：源稿校验/导出在 ``project``，单页操作在
# ``page_api``/``work_objects``，整套计划修订在 ``plan_revision``，OOXML 页面移植
# 在 ``incremental``。JSON 结果报告操作状态；命令成功不等于视觉验收通过。

import json
import sys
from pathlib import Path

from .cli_args import build_parser
from .package import inspect_pptx
from .project import export_project, load_project


def main(argv=None):
    """解析命令并委托给所属模块执行，随后打印结果报告。"""
    parser = build_parser(__doc__)
    args = parser.parse_args(argv)
    try:
        if args.command == "page":
            from .page_api import (
                change_order,
                check_overlap,
                check_page,
                edit_page,
                reshape_pages,
            )

            if args.page_action in ("resume", "rebase"):
                from . import work_objects as work

                result = (
                    work.resume(args.work)
                    if args.page_action == "resume"
                    else work.rebase(args.work, args.page)
                )
            elif args.page_action in ("open", "update"):
                from . import work_objects as work
                from .project import parse_document

                if args.page_action == "open":
                    results = [
                        work.open_page(
                            args.project, n, args.width, render=not args.no_preview
                        )
                        for n in dict.fromkeys(args.page)
                    ]
                    result = (
                        results[0]
                        if len(results) == 1
                        else {
                            "status": "blocked"
                            if any(r["status"] != "ready" for r in results)
                            else "ready",
                            "pages": results,
                        }
                    )
                else:
                    changes = (
                        parse_document(args.changes.read_text(), str(args.changes))
                        if args.changes
                        else None
                    )
                    if bool(args.element) != bool(args.changes):
                        raise ValueError("Use --element with --changes")
                    edits = (
                        parse_document(args.edits.read_text(), str(args.edits))
                        if args.edits
                        else None
                    )
                    layout = (
                        parse_document(args.layout.read_text(), str(args.layout))
                        if args.layout
                        else None
                    )
                    result = work.update(
                        args.work,
                        args.content,
                        args.element,
                        changes,
                        args.candidate,
                        edits=edits,
                        layout=layout,
                        allow_duplicates=args.allow_duplicates,
                    )
            elif (
                args.page_action in ("insert", "split", "merge", "move", "remove")
                and args.token is None
            ):
                from .work_objects import change

                contents = getattr(args, "content", None)
                if contents is not None and not isinstance(contents, list):
                    contents = [contents]
                result = change(
                    args.session,
                    args.page_action,
                    contents or (),
                    other=getattr(args, "next", None) or getattr(args, "anchor", None),
                    position=getattr(args, "position", "after"),
                    allow_duplicates=getattr(args, "allow_duplicates", False),
                )
            elif args.page_action == "check":
                result = check_page(args.project, args.page, args.session, args.width)
            elif args.page_action == "check-text":
                from .typography import check_project

                result = check_project(args.project, args.page, args.output)
            elif args.page_action == "check-overlap":
                result = check_overlap(
                    args.project, args.page, args.output, args.cell_size
                )
            elif args.page_action == "edit":
                result = edit_page(args.session, args.token, args.content)
            elif args.page_action == "split":
                result = reshape_pages(args.session, args.token, args.content)
            elif args.page_action == "merge":
                result = reshape_pages(
                    args.session,
                    args.token,
                    [args.content],
                    args.next_session,
                    args.next_token,
                )
            elif args.page_action == "patch":
                from .project import parse_document

                changes = parse_document(
                    args.changes.read_text(encoding="utf-8"), str(args.changes)
                )
                result = edit_page(
                    args.session, args.token, element_id=args.element, changes=changes
                )
            else:
                result = change_order(
                    args.session,
                    args.token,
                    args.page_action,
                    content=getattr(args, "content", None),
                    position=getattr(args, "position", "after"),
                    anchor_session=getattr(args, "anchor_session", None),
                    anchor_token=getattr(args, "anchor_token", None),
                    allow_duplicates=getattr(args, "allow_duplicates", False),
                )
        elif args.command == "deck":
            if args.deck_action == "preflight":
                from .preflight import check as check_sources

                result = check_sources(
                    args.source,
                    plan=args.plan,
                    settings=args.settings,
                    numbers=args.page,
                    academic=not args.basic,
                    allow_remote=not args.offline,
                )
            elif args.deck_action in ("import-pages", "resume"):
                from . import batch_pages
                from .project import parse_document

                if args.deck_action == "resume":
                    result = batch_pages.resume(args.token)
                else:
                    settings = (
                        parse_document(args.settings.read_text(), str(args.settings))
                        if args.settings
                        else None
                    )
                    result = batch_pages.import_pages(
                        args.project,
                        args.plan,
                        args.request_id,
                        settings=settings,
                        after=args.after,
                        allow_duplicates=args.allow_duplicates,
                        width=args.width,
                    )
            elif args.deck_action == "open":
                from .plan_revision import open_deck

                result = open_deck(
                    args.project,
                    args.page,
                    width=args.width,
                    render=not args.no_preview,
                )
            elif args.deck_action == "review":
                from .review import annotate

                result = annotate(args.directory, args.page, args.status, args.note)
            elif args.deck_action == "revise":
                from .revision import revise

                result = revise(
                    args.project,
                    args.plan,
                    args.output,
                    force=args.force,
                    width=args.width,
                )
            elif args.deck_action == "create":
                from .project import create_project, parse_document

                if args.project is not None:
                    from .work_objects import create

                    if (
                        not args.settings
                        or not args.content
                        or args.draft
                        or args.output
                    ):
                        raise ValueError(
                            "Use deck create PROJECT --settings FILE --content FIRST_PAGE"
                        )
                    result = create(
                        args.project,
                        parse_document(args.settings.read_text(), str(args.settings)),
                        parse_document(args.content.read_text(), str(args.content)),
                    )
                else:
                    if not args.draft or not args.output:
                        raise ValueError(
                            "Use deck create PROJECT --settings FILE --content FIRST_PAGE"
                        )
                    result = create_project(args.draft, args.output)
            elif args.deck_action in ("brief", "directive"):
                from . import narrative
                from .project import parse_document

                revoke = getattr(args, "revoke", None)
                if revoke:
                    if args.content or args.history:
                        raise ValueError(
                            "Revoke cannot be combined with content/history"
                        )
                    result = narrative.save(
                        args.project,
                        "revoke",
                        {"id": revoke, "reference": args.source, "quote": args.quote},
                    )
                elif args.content:
                    if args.history:
                        raise ValueError("Use --history for reading, not writing")
                    result = narrative.save(
                        args.project,
                        args.deck_action,
                        parse_document(args.content.read_text(), str(args.content)),
                    )
                else:
                    if getattr(args, "source", None) or getattr(args, "quote", None):
                        raise ValueError("source/quote require --revoke")
                    result = narrative.inspect(args.project, args.history)
            elif args.deck_action == "outline":
                from .narrative import outline
                from .project import parse_document

                result = outline(
                    args.project,
                    args.page,
                    parse_document(args.content.read_text(), str(args.content))
                    if args.content
                    else None,
                )
            elif args.deck_action == "export":
                result = export_project(
                    args.source,
                    args.output,
                    transition=args.transition,
                    force=args.force,
                    allow_remote=not args.offline,
                    measure_text=True,
                    backend=args.backend,
                )
            else:
                from .page_api import check_deck

                result = check_deck(args.project)
        elif args.command == "install-skill":
            from .installation import install_skill

            result = install_skill(args.target, force=args.force)
        elif args.command == "validate":
            pptd, _ = load_project(args.source)
            from .occupancy import require_pages

            require_pages(pptd["size"], pptd["pages"])
            result = {
                "ok": True,
                "pageCount": len(pptd["pages"]),
                "geometryStatus": "passed",
            }
        elif args.command == "export":
            result = export_project(
                args.source,
                args.output,
                backend=args.backend,
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
        if args.command in ("export", "replace-page"):
            project = args.source if args.command == "export" else args.project
            number = 1 if args.command == "export" else args.page
            result["pageWorkflow"] = {
                "nextCommand": [
                    "ansatz-slide",
                    "page",
                    "check",
                    "--project",
                    str(Path(project).resolve()),
                    "--page",
                    str(number),
                    "--session",
                    str(Path(args.output).resolve().with_suffix(f".page-{number}")),
                ],
                "scope": "Single-page source/preview loop; final PPTX visual review remains separate",
            }
        if not args.full:
            from .output import compact_result

            result = compact_result(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if (
            args.command == "deck"
            and args.deck_action == "preflight"
            and args.strict
            and result.get("warnings")
        ):
            return 1
        if (
            args.command == "page"
            and args.page_action in ("check", "check-overlap")
            and result.get("status", result.get("geometry", {}).get("status"))
            == "blocked"
        ):
            return 1
        if result.get("status") in ("blocked", "conflict", "error"):
            return 1
        return 0
    except Exception as exc:
        if args.command == "deck" and args.deck_action == "preflight":
            print(
                json.dumps(
                    {
                        "format": "source-preflight-v1",
                        "status": "blocked",
                        "stage": "source-only",
                        "errors": 1,
                        "warnings": 0,
                        "issues": [
                            {
                                "page": None,
                                "element": None,
                                "severity": "error",
                                "code": "input-invalid",
                                "message": str(exc),
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        work_command = args.command == "page" and (
            getattr(args, "page_action", None) in ("open", "update", "resume", "rebase")
            or (
                getattr(args, "page_action", None)
                in ("insert", "split", "merge", "move", "remove")
                and args.token is None
            )
        )
        work_command = work_command or (
            args.command == "deck"
            and (
                getattr(args, "deck_action", None)
                in (
                    "outline",
                    "export",
                    "brief",
                    "directive",
                    "revise",
                    "import-pages",
                    "resume",
                    "open",
                    "review",
                )
                or (
                    getattr(args, "deck_action", None) == "create"
                    and args.project is not None
                )
            )
        )
        if work_command:
            from .output import attach

            report = getattr(exc, "report", None)
            source_report = (
                isinstance(report, dict)
                and report.get("format") == "source-preflight-v1"
            )
            print(
                json.dumps(
                    attach(
                        {
                            "format": "page-work-v1",
                            "status": "error",
                            "applied": None,
                            "issues": [
                                {"kind": type(exc).__name__, "message": str(exc)}
                            ],
                            "textFit": None if source_report else report,
                            **({"sourcePreflight": report} if source_report else {}),
                            "work": str(
                                getattr(args, "work", getattr(args, "session", ""))
                            )
                            or None,
                            "next": {
                                "hint": "Correct the input or reopen current sources after an interrupted write; retained work is not deleted."
                            },
                        }
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
