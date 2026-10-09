"""Minimal background job runner for AI work.

AI calls can take 10–60 s, so they never run inside the HTTP request in the
default "thread" mode. Jobs are idempotent (they atomically claim a submission),
so the same job may safely be re-run by `manage.py process_ai_queue` — which is
also how you recover jobs after a server restart, or how you run them from cron
when AI_TASK_MODE=queue. Swap this module for Celery/RQ later without changing
callers: they only use `enqueue(func, *args)`.
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)
_executor = None
_lock = threading.Lock()


def _get_executor():
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=max(1, settings.AI_WORKERS), thread_name_prefix="ai-job")
        return _executor


def _run(func, *args):
    close_old_connections()
    try:
        func(*args)
    except Exception:  # job functions record their own failures; this is a last resort
        logger.exception("AI job %s%s crashed", getattr(func, "__name__", func), args)
    finally:
        close_old_connections()


def enqueue(func, *args):
    mode = settings.AI_TASK_MODE
    if mode == "queue":
        return  # processed by `manage.py process_ai_queue`
    if mode == "sync":
        transaction.on_commit(lambda: func(*args))
        return
    transaction.on_commit(lambda: _get_executor().submit(_run, func, *args))
