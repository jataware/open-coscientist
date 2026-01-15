"""
Centralized logging utilities for open-coscientist dev scripts.

provides:
- File-based console logging with no truncation
- Run-specific log files keyed by task_id/run_id
- Separation of terminal logging (logger.info) from detailed file logging (console.print)
"""

import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

logger = logging.getLogger(__name__)

# global state for current run's file console
_current_run_id: Optional[str] = None
_current_file_console: Optional[Console] = None
_log_file_handle = None
_run_start_time: Optional[datetime] = None

# default logs directory
DEFAULT_LOGS_DIR = Path("logs")


def get_logs_dir() -> Path:
    """Get the directory for log files."""
    logs_dir = Path(os.getenv("COSCIENTIST_LOGS_DIR", str(DEFAULT_LOGS_DIR)))
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def initialize_run_logging(run_id: str) -> None:
    """
    Initialize file-based logging for a specific run.

    args:
        run_id: unique identifier for this run (e.g., task_id from server)
    """
    global _current_run_id, _current_file_console, _log_file_handle, _run_start_time

    _current_run_id = run_id
    _run_start_time = datetime.now()

    logs_dir = get_logs_dir()
    log_file_path = logs_dir / f"{run_id}.log"

    # close previous file handle if exists
    if _log_file_handle:
        _log_file_handle.close()

    # open new log file
    _log_file_handle = open(log_file_path, "w", encoding="utf-8")

    # write start timestamp to file
    _log_file_handle.write(f"=== run started at {_run_start_time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    _log_file_handle.write(f"=== run_id: {run_id} ===\n\n")
    _log_file_handle.flush()

    _current_file_console = Console(
        file=_log_file_handle,
        width=300,  # very large width to prevent truncation
        no_color=False,  # keep colors for readability
        force_terminal=True,  # force terminal mode for rich formatting
        legacy_windows=False,
        soft_wrap=True,  # wrap at word boundaries
        tab_size=4,
    )

    logger.info(f"initialized file logging for run_id={run_id} at {log_file_path}")


def cleanup_run_logging() -> None:
    """cleanup file-based logging for current run."""
    global _current_run_id, _current_file_console, _log_file_handle, _run_start_time

    if _log_file_handle and _run_start_time:
        # write end timestamp to file
        end_time = datetime.now()
        duration = end_time - _run_start_time
        _log_file_handle.write(f"\n\n=== run ended at {end_time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        _log_file_handle.write(f"=== duration: {duration} ===\n")
        _log_file_handle.flush()
        _log_file_handle.close()
        _log_file_handle = None

    _current_run_id = None
    _current_file_console = None
    _run_start_time = None


def get_console() -> Console:
    """
    get the console for detailed logging.

    returns file-based console if run logging is initialized,
    otherwise returns a default console (for backwards compatibility).
    """
    if _current_file_console:
        return _current_file_console
    else:
        # fallback: create default console if not initialized
        # this ensures backwards compatibility if called without initialization
        logger.warning("console requested but run logging not initialized, using default console")
        return Console()


@contextmanager
def run_logging_context(run_id: str):
    """
    context manager for run-specific logging.

    usage:
        with run_logging_context("task_123"):
            console = get_console()
            console.print("this goes to logs/task_123.log")
    """
    initialize_run_logging(run_id)
    try:
        yield
    finally:
        cleanup_run_logging()


def get_current_run_id() -> Optional[str]:
    """get the current run id, if any."""
    return _current_run_id
