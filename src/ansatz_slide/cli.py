"""One Python CLI for validation, export, single-page replacement, inspection and page review."""

import argparse
import json
import sys
from pathlib import Path

from .inspection import inspect_pptx
from .project import export_project, load_project


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ansatz-slide", description=__doc__)
    parser.add_argument("--version", action="version", version="ansatz-slide 0.0.1")
    parser.add_argument("--compact", action="store_true", help="Summarize work evidence on stdout; full result remains in the work directory")
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
    page = commands.add_parser("page", help="Inspect and edit one source page at a time")
    page_actions = page.add_subparsers(dest="page_action", required=True)
    open_page = page_actions.add_parser("open", help="Open a page work object with candidate, matrices and preview")
    open_page.add_argument("project",type=Path)
    open_page.add_argument("--page",required=True,type=int,action="append",help="Repeat to open several independent pages in one call")
    open_page.add_argument("--no-preview",action="store_true",help="Read for editing without rendering the old page; update still renders and validates")
    open_page.add_argument("--width",type=int,default=1600)
    update_page = page_actions.add_parser("update", help="Update or retry the retained candidate in a revision-bound work object")
    update_page.add_argument("work",type=Path)
    update_page.add_argument("--content",type=Path)
    update_page.add_argument("--element")
    update_page.add_argument("--changes",type=Path)
    update_page.add_argument("--allow-duplicates",action="store_true",help="Explicitly permit a retained duplicate insertion")
    update_page.add_argument("--candidate",type=int,default=1)
    update_page.add_argument("--edits",type=Path,help="List of element/changes patches applied as one checked page revision")
    update_page.add_argument("--layout",type=Path,help="Deterministic row/column/group/weighted-segment layout of existing elements")
    for name in ('resume','rebase'):
        recovery=page_actions.add_parser(name,help='Recover the latest retained work without publishing')
        recovery.add_argument('work',type=Path)
        if name=='rebase':recovery.add_argument('--page',type=int)
    check_page = page_actions.add_parser("check", help="Expose one page, its rendered preview and bounded context")
    check_page.add_argument("--project", required=True, type=Path)
    check_page.add_argument("--page", required=True, type=int)
    check_page.add_argument("--session", required=True, type=Path)
    check_page.add_argument("--width", type=int, default=1600)
    geometry = page_actions.add_parser("check-overlap", help="Generate occupancy matrices and grayscale bounds maps without an Office renderer")
    geometry.add_argument("--project", type=Path, required=True)
    geometry.add_argument("--page", type=int, required=True)
    geometry.add_argument("--output", type=Path, required=True, help="New output directory")
    geometry.add_argument("--cell-size", type=float, default=1, help="Canvas units per matrix cell")
    edit_page = page_actions.add_parser("edit", help="Replace only the page pinned by check; return its new preview")
    edit_page.add_argument("session", type=Path)
    edit_page.add_argument("--token", required=True)
    edit_page.add_argument("--content", type=Path, help="One .page.yaml object; default is the session's editable page")
    split = page_actions.add_parser("split", help="Replace one checked page with multiple pages in manifest order")
    split.add_argument("session", type=Path)
    split.add_argument("--token", help="Legacy session token")
    split.add_argument("--content", action="append", type=Path, required=True)
    merge = page_actions.add_parser("merge", help="Merge two separately checked adjacent pages")
    merge.add_argument("session", type=Path)
    merge.add_argument("--token", help="Legacy session token")
    merge.add_argument("--next-session", type=Path)
    merge.add_argument("--next",type=Path,help="Adjacent page work reference")
    merge.add_argument("--next-token")
    merge.add_argument("--content", type=Path, required=True)
    patch = page_actions.add_parser("patch", help="Update fields of one element by ID and return a fresh page preview")
    patch.add_argument("session", type=Path)
    patch.add_argument("--token", required=True)
    patch.add_argument("--element", required=True)
    patch.add_argument("--changes", type=Path, required=True, help="JSON/YAML object of element fields; nested maps merge, arrays replace")
    for name in ("insert", "move", "remove"):
        action = page_actions.add_parser(name, help=f"{name.capitalize()} one page in manifest order; retain existing source files")
        action.add_argument("session", type=Path)
        action.add_argument("--token",help="Legacy session token")
        if name != "remove":
            action.add_argument("--position", choices=("before", "after"), default="after")
        if name == "insert":
            action.add_argument("--content", type=Path, required=True)
            action.add_argument("--allow-duplicates",action="store_true")
        if name == "move":
            action.add_argument("--anchor-session", type=Path)
            action.add_argument("--anchor",type=Path,help="Anchor page work reference")
            action.add_argument("--anchor-token")
    text_check = page_actions.add_parser("check-text",help="Measure native text with actual fonts and line layout")
    text_check.add_argument("--project",required=True,type=Path)
    text_check.add_argument("--page",required=True,type=int)
    text_check.add_argument("--output",required=True,type=Path)
    deck = commands.add_parser("deck", help="Read the outline or publish a checked draft manifest")
    deck_actions = deck.add_subparsers(dest="deck_action", required=True)
    batch=deck_actions.add_parser('import-pages',help='Create/insert an ordered batch with idempotency and retained candidates')
    batch.add_argument('project',type=Path)
    batch.add_argument('--plan',type=Path,required=True)
    batch.add_argument('--request-id',required=True)
    batch.add_argument('--settings',type=Path)
    batch.add_argument('--after',type=int)
    batch.add_argument('--allow-duplicates',action='store_true')
    batch.add_argument('--width',type=int,default=1600)
    resume_deck=deck_actions.add_parser('resume',help='Resume a retained batch; applied requests never insert twice')
    resume_deck.add_argument('token',type=Path)
    check_deck = deck_actions.add_parser("check")
    check_deck.add_argument("--project", required=True, type=Path)
    create_deck = deck_actions.add_parser("create", help="Precheck every draft page before creating the formal pptx.yaml manifest")
    create_deck.add_argument("project",nargs="?",type=Path)
    create_deck.add_argument("--settings",type=Path)
    create_deck.add_argument("--content",type=Path,help="First page candidate")
    create_deck.add_argument("--draft",type=Path,help="Legacy draft manifest publication")
    create_deck.add_argument("--output",type=Path)
    outline_deck=deck_actions.add_parser("outline",help="Read or record model-authored purpose, claim, evidence and connection")
    outline_deck.add_argument("project",type=Path)
    outline_deck.add_argument("--page",type=int)
    outline_deck.add_argument("--content",type=Path)
    for name in ('brief','directive'):
        action=deck_actions.add_parser(name,help='Read or record deck argument and attributed directives')
        action.add_argument('project',type=Path)
        action.add_argument('--content',type=Path)
        action.add_argument('--history',action='store_true')
        if name=='directive':
            action.add_argument('--revoke',help='Revoke one directive ID, preserving history')
            action.add_argument('--source',help='Reference for the revocation instruction')
            action.add_argument('--quote',help='Exact relevant text from the revocation instruction')
    export_deck=deck_actions.add_parser("export",help="Export current checked sources")
    export_deck.add_argument("source",type=Path)
    export_deck.add_argument("-o","--output",type=Path,required=True)
    export_deck.add_argument("--force",action="store_true")
    export_deck.add_argument("--offline",action="store_true")
    export_deck.add_argument("--transition",choices=("none","fade"),default="none")
    revise_deck=deck_actions.add_parser("revise",help="Apply a version-bound page plan, export once and render final previews")
    revise_deck.add_argument("project",type=Path)
    revise_deck.add_argument("--plan",type=Path,required=True)
    revise_deck.add_argument("-o","--output",type=Path,required=True)
    revise_deck.add_argument("--force",action="store_true")
    revise_deck.add_argument("--width",type=int,default=1600)
    args = parser.parse_args(argv)
    try:
        if args.command == "page":
            from .page_api import check_page, edit_page, reshape_pages, change_order, check_overlap
            if args.page_action in ('resume','rebase'):
                from . import work_objects as work
                result=work.resume(args.work) if args.page_action=='resume' else work.rebase(args.work,args.page)
            elif args.page_action in ("open","update"):
                from . import work_objects as work
                from .project import parse_document
                if args.page_action=="open":
                    results=[work.open_page(args.project,n,args.width,render=not args.no_preview) for n in dict.fromkeys(args.page)]
                    result=results[0] if len(results)==1 else {'status':'blocked' if any(r['status']!='ready' for r in results) else 'ready','pages':results}
                else:
                    changes=parse_document(args.changes.read_text(),str(args.changes)) if args.changes else None
                    if bool(args.element)!=bool(args.changes):raise ValueError("Use --element with --changes")
                    edits=parse_document(args.edits.read_text(),str(args.edits)) if args.edits else None
                    layout=parse_document(args.layout.read_text(),str(args.layout)) if args.layout else None
                    result=work.update(args.work,args.content,args.element,changes,args.candidate,edits=edits,layout=layout,allow_duplicates=args.allow_duplicates)
            elif args.page_action in ("insert","split","merge","move","remove") and args.token is None:
                from .work_objects import change
                contents=getattr(args,"content",None)
                if contents is not None and not isinstance(contents,list):contents=[contents]
                result=change(args.session,args.page_action,contents or (),
                              other=getattr(args,"next",None) or getattr(args,"anchor",None),
                              position=getattr(args,"position","after"),allow_duplicates=getattr(args,'allow_duplicates',False))
            elif args.page_action == "check":
                result = check_page(args.project, args.page, args.session, args.width)
            elif args.page_action == "check-text":
                from .typography import check_project
                result=check_project(args.project,args.page,args.output)
            elif args.page_action == "check-overlap":
                result = check_overlap(args.project, args.page, args.output, args.cell_size)
            elif args.page_action == "edit":
                result = edit_page(args.session, args.token, args.content)
            elif args.page_action == "split":
                result = reshape_pages(args.session, args.token, args.content)
            elif args.page_action == "merge":
                result = reshape_pages(args.session, args.token, [args.content], args.next_session, args.next_token)
            elif args.page_action == "patch":
                from .project import parse_document
                changes = parse_document(args.changes.read_text(encoding="utf-8"), str(args.changes))
                result = edit_page(args.session, args.token, element_id=args.element, changes=changes)
            else:
                result = change_order(args.session, args.token, args.page_action,
                    content=getattr(args, "content", None), position=getattr(args, "position", "after"),
                    anchor_session=getattr(args, "anchor_session", None), anchor_token=getattr(args, "anchor_token", None),allow_duplicates=getattr(args,"allow_duplicates",False))
        elif args.command == "deck":
            if args.deck_action in ('import-pages','resume'):
                from . import batch_pages
                from .project import parse_document
                if args.deck_action=='resume':result=batch_pages.resume(args.token)
                else:
                    settings=parse_document(args.settings.read_text(),str(args.settings)) if args.settings else None
                    result=batch_pages.import_pages(args.project,args.plan,args.request_id,settings=settings,after=args.after,allow_duplicates=args.allow_duplicates,width=args.width)
            elif args.deck_action=='revise':
                from .revision import revise
                result=revise(args.project,args.plan,args.output,force=args.force,width=args.width)
            elif args.deck_action=='create':
                from .project import create_project, parse_document
                if args.project is not None:
                    from .work_objects import create
                    if not args.settings or not args.content or args.draft or args.output:raise ValueError("Use deck create PROJECT --settings FILE --content FIRST_PAGE")
                    result=create(args.project,parse_document(args.settings.read_text(),str(args.settings)),
                                  parse_document(args.content.read_text(),str(args.content)))
                else:
                    if not args.draft or not args.output:raise ValueError("Use deck create PROJECT --settings FILE --content FIRST_PAGE")
                    result=create_project(args.draft,args.output)
            elif args.deck_action in ('brief','directive'):
                from . import narrative
                from .project import parse_document
                revoke=getattr(args,'revoke',None)
                if revoke:
                    if args.content or args.history:raise ValueError('Revoke cannot be combined with content/history')
                    result=narrative.save(args.project,'revoke',{'id':revoke,'reference':args.source,'quote':args.quote})
                elif args.content:
                    if args.history:raise ValueError('Use --history for reading, not writing')
                    result=narrative.save(args.project,args.deck_action,parse_document(args.content.read_text(),str(args.content)))
                else:
                    if getattr(args,'source',None) or getattr(args,'quote',None):raise ValueError('source/quote require --revoke')
                    result=narrative.inspect(args.project,args.history)
            elif args.deck_action=='outline':
                from .outline import outline
                from .project import parse_document
                result=outline(args.project,args.page,parse_document(args.content.read_text(),str(args.content)) if args.content else None)
            elif args.deck_action=='export':
                result=export_project(args.source,args.output,transition=args.transition,force=args.force,allow_remote=not args.offline,measure_text=True)
            else:
                from .page_api import check_deck
                result = check_deck(args.project)
        elif args.command == "install-skill":
            from .installation import install_skill
            result = install_skill(args.target, force=args.force)
        elif args.command == "validate":
            pptd, _ = load_project(args.source)
            from .occupancy import require_pages
            require_pages(pptd['size'],pptd['pages'])
            result = {"ok": True, "pageCount": len(pptd["pages"]), "geometryStatus":"passed"}
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
        if args.command in ("export", "replace-page"):
            project = args.source if args.command == "export" else args.project
            number = 1 if args.command == "export" else args.page
            result["pageWorkflow"] = {
                "nextCommand": ["ansatz-slide", "page", "check", "--project", str(Path(project).resolve()),
                                "--page", str(number), "--session",
                                str(Path(args.output).resolve().with_suffix(f".page-{number}"))],
                "scope": "Single-page source/preview loop; final PPTX visual review remains separate",
            }
        if args.compact:
            from .output import compact_result
            result=compact_result(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if (args.command=='page' and args.page_action in ('check','check-overlap') and
                result.get('status',result.get('geometry',{}).get('status'))=='blocked'):
            return 1
        if result.get('status') in ('blocked','conflict','error'):return 1
        return 0
    except Exception as exc:
        work_command=(args.command=='page' and (getattr(args,'page_action',None) in ('open','update','resume','rebase') or
                      (getattr(args,'page_action',None) in ('insert','split','merge','move','remove') and args.token is None)))
        work_command=work_command or (args.command=='deck' and (getattr(args,'deck_action',None) in ('outline','export','brief','directive','revise','import-pages','resume') or
                                                              (getattr(args,'deck_action',None)=='create' and args.project is not None)))
        if work_command:
            from .gates import attach
            print(json.dumps(attach({'format':'page-work-v1','status':'error','applied':None,
                              'issues':[{'kind':type(exc).__name__,'message':str(exc)}],
                              'textFit':getattr(exc,'report',None),
                              'work':str(getattr(args,'work',getattr(args,'session',''))) or None,
                              'next':{'hint':'Correct the input or reopen current sources after an interrupted write; retained work is not deleted.'}}),ensure_ascii=False,indent=2))
            return 1
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
