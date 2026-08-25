import os

# Single source of truth is VERSION.txt (copied to /app/VERSION.txt by the
# Dockerfile) -- __version__ used to be a hardcoded literal here, separate
# from VERSION.txt, so bumping the file silently did nothing: the app kept
# reporting the old baked-in string. Found via deploy-architecture-A's
# rollback proof: two builds with different VERSION.txt both reported the
# same /api/system/ready version. Fall back to the old literal only if the
# file is somehow missing (e.g. a non-Docker dev run from source).
_VERSION_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'VERSION.txt')
try:
    with open(_VERSION_FILE) as _f:
        __version__ = _f.read().strip()
except OSError:
    __version__ = '71.0.0.65-kiosk-v2-vn-font'
