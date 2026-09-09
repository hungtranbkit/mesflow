"""Hàng chờ sửa page is wired end to end (menu -> permission -> API -> RBAC).

The 2026-09-09 audit found migration 0044's rework queue shipped with a
working backend and no interface whatsoever -- 13 items pending on TEST and
zero resolutions, because resolving one meant POSTing by hand. These
contracts keep the page attached to everything it needs.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "mesflow" / "web" / "static"


def source(path): return (ROOT / path).read_text(encoding="utf-8")


def test_page_is_registered_and_reachable():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    page = (STATIC / "pages" / "rework-queue.js").read_text(encoding="utf-8")
    template = source("app/mesflow/web/templates/app.html")
    assert "page:'rework-queue'" in app
    assert "'rework-queue':'rework.view'" in app
    assert "registerPage('rework-queue'" in page
    assert "/static/pages/rework-queue.js" in template
    # Calls the real endpoints, including the idempotency key resolve() needs.
    assert "/api/rework/queue" in page
    assert "/resolve" in page and "request_id" in page


def test_pages_register_instead_of_monkey_patching_open_page():
    """openPage owns the permission check, setActive and the ?page= sync.

    Two pages used to wrap it (`const prev=openPage; openPage=(id,btn)=>...`),
    which dropped its third argument and skipped the URL sync entirely, so
    Production Trace and Báo cáo năng suất had no URL of their own.
    """
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "PAGE_RENDERERS" in app and "window.registerPage" in app
    for name in ("production-trace", "employee-productivity", "rework-queue"):
        page = (STATIC / "pages" / f"{name}.js").read_text(encoding="utf-8")
        assert f"registerPage('{name}'" in page, name
        assert "openPage=async function" not in page.replace(" ", ""), name


def test_api_and_rbac_agree_with_the_page():
    routes = source("app/mesflow/web/execution.py")
    auth = source("app/mesflow/web/auth.py")
    rbac = source("app/mesflow/db/repositories/rbac.py")
    migration = source("app/migrations/versions/0045_rework_queue_permissions.py")
    # Reading the queue is gated by the same permission that shows the page.
    assert "@permission_required('rework.view')" in routes
    assert "('/api/rework','rework.resolve' if edit else 'rework.view')" in auth
    assert "('rework.view'," in rbac and "('rework.resolve'," in rbac
    # Seed alone cannot grant on an existing install (it skips any role that
    # already has grants), so the migration must hand out the grants too.
    assert "rbac_role_permissions" in migration
    for role in ("admin", "manager", "supervisor"):
        assert role in migration
