import os

# Single source of truth is VERSION.txt (copied to /app/VERSION.txt by the
# Dockerfile) -- __version__ used to be a hardcoded literal here, separate
# from VERSION.txt, so bumping the file silently did nothing: the app kept
# reporting the old baked-in string. Found via deploy-architecture-A's
# rollback proof: two builds with different VERSION.txt both reported the
# same /api/system/ready version. Fall back to the old literal only if the
# file is somehow missing (e.g. a non-Docker dev run from source).
#
# Two on-disk layouts both need to resolve correctly here (issue #25
# follow-up, 2026-09-07): the real Dockerfile does `WORKDIR /app` +
# `COPY app /app` + `COPY VERSION.txt /app/VERSION.txt`, so this package
# lives at /app/mesflow/__init__.py and VERSION.txt is exactly 2
# dirname() hops up (a sibling of the mesflow/ package dir). A plain host
# checkout (bare `pytest`, no Docker) keeps the repo's own extra `app/`
# nesting that `COPY app /app` normally flattens away, so the real
# VERSION.txt there is one hop further up, at 3 hops. Try both -- 2-hop
# (container layout) first since that's the real deployed shape, then
# 3-hop (host-checkout layout) -- instead of assuming only one. Without
# this, every release-contract test that imports mesflow and asserts
# __version__ against VERSION.txt was silently guaranteed to fail on any
# bare host/CI-outside-Docker run, independent of whether VERSION.txt
# itself was correct.
_INIT_DIR = os.path.dirname(__file__)
_VERSION_FILE_CANDIDATES = (
    os.path.join(os.path.dirname(_INIT_DIR), 'VERSION.txt'),
    os.path.join(os.path.dirname(os.path.dirname(_INIT_DIR)), 'VERSION.txt'),
)
__version__ = '71.0.0.65-kiosk-v2-vn-font'
for _candidate in _VERSION_FILE_CANDIDATES:
    try:
        with open(_candidate) as _f:
            __version__ = _f.read().strip()
        break
    except OSError:
        continue
