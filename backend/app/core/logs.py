"""The one line form of `backend`, `migrate` and `worker`, and the hooks that keep every line in it.

ADR-0005 addendum of 2026-11-02 (*`backend`, `migrate` and `worker`: one line form*); the form is
documented in docs/operations/log-format.md. Standard library only: `core` depends on no layer.

Each line is one JSON object on standard error, ASCII-escaped, so no value splits or forges a
line. An exception is written as its type and code location only, whether it reaches a record as
`exc_info`, as the message or as an argument. A record of a logger outside `app` is written with
its format string: its arguments are never interpolated (Q-5 A). No setting is read from the
environment (ADR-0001-C10), and the time of a line is the record's own.
"""

import json
import logging
import logging.config
import sys
import threading
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

PROCESSES = ("backend", "migrate", "worker")
BACKEND_ROOT = Path(__file__).resolve().parents[2]
_APPLICATION_DIRS = ("app", "migrations")
# Bound by the request handling (app.main) for the time a request is handled.
correlation_id: ContextVar[str | None] = ContextVar("eko_correlation_id", default=None)

ExcInfo = tuple[type[BaseException], BaseException | None, TracebackType | None]


@dataclass(frozen=True)
class RequestLine:
    """The fields of one request line; passed as `extra={"eko_request": RequestLine(...)}`."""

    method: str
    route: str
    status: int
    duration_ms: float
    correlation_id: str


def type_name(kind: type[BaseException]) -> str:
    return f"{kind.__module__}.{kind.__qualname__}"


def _module_of(filename: str, frame_module: str) -> str | None:
    """The module part of a code location, or None when the frame is not the application's."""
    try:
        relative = Path(filename).resolve().relative_to(BACKEND_ROOT)
    except (ValueError, OSError):
        return None
    if not relative.parts or relative.parts[0] not in _APPLICATION_DIRS:
        return None
    if relative.parts[0] == "migrations":
        return relative.as_posix()
    dotted = ".".join(relative.with_suffix("").parts)
    return dotted.removesuffix(".__init__") or frame_module


def code_location(traceback: TracebackType | None) -> str:
    """`<module>:<function>:<line>` of the innermost frame of the application's own code, else of
    the innermost frame; `unknown` for an exception that was never raised."""
    frames = []
    while traceback is not None:
        frames.append((traceback.tb_frame, traceback.tb_lineno))
        traceback = traceback.tb_next
    if not frames:
        return "unknown"
    for frame, line in reversed(frames):
        module = _module_of(frame.f_code.co_filename, str(frame.f_globals.get("__name__", "")))
        if module is not None:
            return f"{module}:{frame.f_code.co_qualname}:{line}"
    frame, line = frames[-1]
    return f"{frame.f_globals.get('__name__', '?')}:{frame.f_code.co_qualname}:{line}"


def error_fields(info: ExcInfo) -> dict[str, str]:
    kind, value, traceback = info
    fields = {"error": type_name(kind), "at": code_location(traceback)}
    if value is not None:
        cause = value.__cause__
        if cause is None and not value.__suppress_context__:
            cause = value.__context__
        if cause is not None:
            fields["cause"] = type_name(type(cause))
    return fields


def _exception_of(record: logging.LogRecord) -> ExcInfo | None:
    hooked = getattr(record, "eko_exc", None)
    if isinstance(hooked, tuple) and len(hooked) == 3 and isinstance(hooked[0], type):
        return hooked[0], hooked[1], hooked[2]
    if record.exc_info and record.exc_info[0] is not None:
        kind, value, traceback = record.exc_info
        return kind, value, traceback
    args = record.args.values() if isinstance(record.args, dict) else (record.args or ())
    for candidate in (record.msg, *args):
        if isinstance(candidate, BaseException):
            return type(candidate), candidate, candidate.__traceback__
    return None


def _is_application(name: str) -> bool:
    return name == "app" or name.startswith("app.")


def _message(record: logging.LogRecord) -> str:
    if not isinstance(record.msg, str):
        return f"<{type(record.msg).__qualname__}>"
    if not _is_application(record.name):
        return record.msg
    try:
        return record.getMessage()
    except (TypeError, ValueError, KeyError):
        # A message whose arguments do not fit its format: the format string alone.
        return record.msg


class LineFormatter(logging.Formatter):
    """Formats every record as the documented JSON line; never the message's traceback."""

    def __init__(self, process: str) -> None:
        super().__init__()
        if process not in PROCESSES:
            raise ValueError(f"unknown process {process!r}")
        self.process = process

    def format(self, record: logging.LogRecord) -> str:
        created = datetime.fromtimestamp(record.created, UTC)
        line: dict[str, Any] = {
            "ts": created.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "process": self.process,
            "logger": record.name,
        }
        request = getattr(record, "eko_request", None)
        info = _exception_of(record)
        current = correlation_id.get()
        if isinstance(request, RequestLine):
            line["event"] = "request"
            line.update(
                method=request.method,
                route=request.route,
                status=request.status,
                duration_ms=request.duration_ms,
                correlation_id=request.correlation_id,
            )
        elif info is not None:
            line["event"] = "error"
            line.update(error_fields(info))
            if current is not None:
                line["correlation_id"] = current
        else:
            line["event"] = "message"
            line["msg"] = _message(record)
            if current is not None:
                line["correlation_id"] = current
        return json.dumps(line, ensure_ascii=True, separators=(",", ":"))


def log_config(process: str) -> dict[str, Any]:
    """The logging configuration of a process; `serve.py` passes it to uvicorn as `log_config`,
    which applies it in every worker process before the factory is imported."""
    if process not in PROCESSES:
        raise ValueError(f"unknown process {process!r}")
    quiet = {"level": "WARNING", "handlers": [], "propagate": True}
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"line": {"()": f"{__name__}.LineFormatter", "process": process}},
        "handlers": {
            "stderr": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "formatter": "line",
            }
        },
        "root": {"level": "WARNING", "handlers": ["stderr"]},
        "loggers": {
            "app": {"level": "INFO", "handlers": [], "propagate": True},
            "uvicorn": quiet,
            "uvicorn.error": {"level": "INFO", "handlers": [], "propagate": True},
            "uvicorn.access": quiet,
            "uvicorn.asgi": quiet,
        },
    }


_unhandled = logging.getLogger("app.unhandled")


def _excepthook(
    kind: type[BaseException], value: BaseException, traceback: TracebackType | None
) -> None:
    _unhandled.error("unhandled exception", extra={"eko_exc": (kind, value, traceback)})


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit:
        return
    hooked = (args.exc_type, args.exc_value, args.exc_traceback)
    _unhandled.error("unhandled exception in a thread", extra={"eko_exc": hooked})


def _unraisablehook(unraisable: "sys.UnraisableHookArgs") -> None:
    hooked = (unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback)
    _unhandled.error("unraisable exception", extra={"eko_exc": hooked})


def install_process_logging(process: str) -> None:
    """The process half of the line form: the configuration and the interpreter's hooks."""
    logging.config.dictConfig(log_config(process))
    # A failing handler would otherwise print the record's message and arguments.
    logging.raiseExceptions = False
    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    sys.unraisablehook = _unraisablehook
    logging.captureWarnings(True)
