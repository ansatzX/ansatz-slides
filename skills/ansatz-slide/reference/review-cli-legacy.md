# Compatibility commands

Use [work objects](review-cli.md) for new authoring. These interfaces remain for existing integrations. They require explicit sessions/tokens and do not implement the work-chain layout freeze or three-failure guidance. Shared schema, geometry and source publication checks still apply.

## Check and edit a page

```bash
ansatz-slide page check --project ./deck --page 2 --session ./work/page-2
ansatz-slide page edit ./work/page-2 --token TOKEN --content ./candidate.page.yaml
ansatz-slide page patch ./work/page-2 --token TOKEN --element body --changes ./fields.yaml
```

`TOKEN` is the latest returned token, not a literal. The session pins one page and exposes `editablePage`, `pageSource`, geometry and preview paths. `page edit` without `--content` reads the session draft. Element patches recursively merge maps and replace arrays, preserving omitted fields; element identity/type cannot change.

Use the new returned token after success. A pending edited draft cannot be silently discarded by checking or patching again. Reuse it deliberately or choose a new session. A source/global-setting/related-asset change makes old tokens stale. Source aliases that would edit multiple positions are rejected.

Blocked geometry retains the draft and diagnostics, returns no Office image/PPTX, and exits nonzero. Successful edit/patch updates one formal source and its preview, not a full-deck PPTX. Follow the shared [geometry and recovery rules](review-cli.md).

## Structural changes

Each example needs freshly checked sessions and their actual tokens:

```bash
ansatz-slide page insert ./work/page-2 --token TOKEN --content ./new.page.yaml --position after
ansatz-slide page split ./work/page-2 --token TOKEN --content ./a.page.yaml --content ./b.page.yaml
ansatz-slide page merge ./work/page-2 --token TOKEN --next-session ./work/page-3 --next-token NEXT_TOKEN --content ./combined.page.yaml
ansatz-slide page move ./work/page-2 --token TOKEN --anchor-session ./work/destination --anchor-token ANCHOR_TOKEN --position before
ansatz-slide page remove ./work/page-2 --token TOKEN
```

Merge requires the immediately following page. Move uses the checked anchor identity. Structural changes validate the resulting page set, retain retired sources, and invalidate old manifest tokens; use the returned next command. The last remaining page cannot be removed. Export the deck after source pagination.

## Draft manifest and outline summary

```bash
ansatz-slide deck create --draft ./deck/deck.draft.yaml --output ./deck/pptx.yaml
ansatz-slide deck check --project ./deck
```

Draft creation accepts explicit page paths, requires all pages to pass geometry and requires a directory with no existing formal manifest. Draft/output share a directory; output must be new and named `pptx.yaml` or `*.pptx.yaml`. It does not perform the new work-object creation preview. Use `deck create PROJECT --settings FILE --content FILE` when starting a new authoring flow.

`deck check` is a read-only ordered title/source summary, not semantic review or an editable full-deck payload. For model-authored intent use `deck outline`.

## Export

`export PROJECT -o FILE` is retained and defaults to fade; `deck export` defaults to none. Both accept explicit `--transition`, `--offline` and `--force`. Binary replacement has its own [procedure](page-edit.md).

Sessions and current work objects share kernel-owned locks. Process exit releases ownership; persistent lock files must not be manually removed. Recovery and filesystem limitations are documented once in [the work-object reference](review-cli.md). Do not edit session state files or bypass failed scoped operations with bulk source writes.
