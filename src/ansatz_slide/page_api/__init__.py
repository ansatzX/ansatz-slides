"""页面操作入口；状态、渲染检查和发布事务分别由子模块负责。"""

from .. import export_pptx
from ..file_transactions import preserving_replace
from ..package import inspect_pptx
from ..project import image_objects, resolve_images
from ..typography import check_page as measure_text
from ..typography import check_pages as measure_pages
from ..validation import safe_path
from .checks import check_deck, check_overlap, preview, preview_batch, response
from .operations import (
    change_order,
    check_page,
    checked_state,
    edit_page,
    patch_element,
    publish_order,
    reshape_pages,
)
from .state import (
    context,
    json_bytes,
    lock,
    page_fingerprint,
    page_token,
    presentation_token,
    session_path,
    session_write,
    sha,
    snapshot,
    title,
    unchanged,
)

__all__ = [
    "change_order",
    "check_deck",
    "check_overlap",
    "check_page",
    "checked_state",
    "context",
    "edit_page",
    "export_pptx",
    "image_objects",
    "inspect_pptx",
    "json_bytes",
    "lock",
    "measure_pages",
    "measure_text",
    "page_fingerprint",
    "page_token",
    "patch_element",
    "presentation_token",
    "preserving_replace",
    "preview",
    "preview_batch",
    "publish_order",
    "reshape_pages",
    "resolve_images",
    "response",
    "safe_path",
    "session_path",
    "session_write",
    "sha",
    "snapshot",
    "title",
    "unchanged",
]
