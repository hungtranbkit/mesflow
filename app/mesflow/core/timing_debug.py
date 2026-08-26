"""Reliability Validation Round 2, FIX 2 -- lightweight, opt-in stage
timing for the START/FINISH critical path, to profile write contention
(Gate 13's confirmed capacity ceiling) without permanently spamming
production logs.

Off by default (MESFLOW_TIMING_DEBUG unset/'0'). When enabled, each
stage() call records elapsed milliseconds under a name; StageTimer.emit()
logs the whole breakdown as ONE structured line per request, to the
`mesflow.timing` logger -- easy to grep/aggregate, easy to disable.

Usage:
    timer = StageTimer('session_start')
    with timer.stage('overlap_check'):
        ...
    with timer.stage('insert'):
        ...
    timer.emit(session_id=row['id'])
"""
from __future__ import annotations

import contextlib
import logging
import os
import time
from typing import Any

logger = logging.getLogger('mesflow.timing')


def _enabled() -> bool:
    on = os.environ.get('MESFLOW_TIMING_DEBUG', '0').strip().lower() in {'1', 'true', 'yes', 'on'}
    if on and not logger.handlers:
        # The app never calls logging.basicConfig() (see web/app.py), so the
        # root logger's default level (WARNING) would silently swallow every
        # .info() call below. Configure ONLY this logger, once, so enabling
        # the env var is guaranteed to actually produce output regardless of
        # whatever else does or doesn't configure logging elsewhere.
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return on


class StageTimer:
    """No-op (near-zero overhead) unless MESFLOW_TIMING_DEBUG is set --
    checked once at construction, not per-stage, so a disabled timer costs
    one attribute check per stage() call and nothing else."""

    def __init__(self, operation: str):
        self.operation = operation
        self.enabled = _enabled()
        self.stages: dict[str, float] = {}
        self._t0 = time.perf_counter() if self.enabled else 0.0

    @contextlib.contextmanager
    def stage(self, name: str):
        if not self.enabled:
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = round((time.perf_counter() - start) * 1000, 2)

    def emit(self, **extra: Any) -> None:
        if not self.enabled:
            return
        total_ms = round((time.perf_counter() - self._t0) * 1000, 2)
        logger.info('timing operation=%s total_ms=%s stages=%s %s', self.operation, total_ms, self.stages, extra)
