"""Keys must land neither in logs nor in stored status texts (rule: keys only in .env).

Two layers of protection: (1) known secret values from the settings are replaced everywhere, (2) URL parameters with
typical key names (token, apikey, ...) are replaced regardless of the value. In addition, the
HTTP client logging (httpx/httpcore), which prints complete request URLs, is set to WARNING."""
import logging
import re
import sys

from app.config import get_settings

MASK = "***"
_MIN_SECRET_LEN = 6
_NAME_HINTS = ("key", "secret", "token", "password")
_PARAM_RE = re.compile(
    r"(?i)([?&\s\"'])(token|api_?key|api_?token|access_?token|key|secret|password)=([^&\s\"']+)")
_installed = False


def secret_values() -> list[str]:
    """All configured secret values (from .env), longest first so partial values leave nothing behind."""
    values = {
        v.strip() for name, v in get_settings().model_dump().items()
        if isinstance(v, str) and any(h in name for h in _NAME_HINTS) and len(v.strip()) >= _MIN_SECRET_LEN
    }
    return sorted(values, key=len, reverse=True)


def redact(text: str) -> str:
    for secret in secret_values():
        text = text.replace(secret, MASK)
    return _PARAM_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}={MASK}", text)


def _plain_args(args: object) -> bool:
    """Only tuples of text and numbers may be cleaned individually; everything else (objects, exceptions, mappings)
    is formatted first, because only the text shows whether a secret is in it."""
    plain = (str, int, float, bool, type(None))
    return isinstance(args, tuple) and len(args) > 0 and all(isinstance(a, plain) for a in args)


def install() -> None:
    """Call once per process (API, worker, backtest job): every log entry is cleaned when it is created,
    including tracebacks. Applies to all loggers and handlers, including those of uvicorn."""
    global _installed
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    if _installed:
        return
    _installed = True
    factory = logging.getLogRecordFactory()

    def make_record(*args, **kwargs):  # type: ignore[no-untyped-def]
        rec = factory(*args, **kwargs)
        try:
            if _plain_args(rec.args):
                # keep the structure of the arguments: uvicorn's access formatter unpacks record.args itself
                rec.msg = redact(str(rec.msg))
                rec.args = tuple(redact(a) if isinstance(a, str) else a for a in rec.args)  # type: ignore[union-attr]
            else:
                rec.msg, rec.args = redact(rec.getMessage()), None
            if rec.exc_info and not rec.exc_text:
                rec.exc_text = redact(logging.Formatter().formatException(rec.exc_info))
            elif rec.exc_text:
                rec.exc_text = redact(rec.exc_text)
            if rec.stack_info:
                rec.stack_info = redact(rec.stack_info)
        except Exception:  # logging must never disturb the application
            rec.msg, rec.args = "[log entry suppressed because of a redaction error]", None
            rec.exc_info = rec.exc_text = None
        return rec

    logging.setLogRecordFactory(make_record)
    # Errors outside logging (e.g. an unhandled exception in the main thread) go through excepthook

    def safe_hook(exc_type, exc, tb):  # type: ignore[no-untyped-def]
        import traceback
        sys.stderr.write(redact("".join(traceback.format_exception(exc_type, exc, tb))))

    sys.excepthook = safe_hook
