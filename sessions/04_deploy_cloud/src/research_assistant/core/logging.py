"""Application logs: plain text on stdout (12-factor), every line tagged with the request it belongs to.

The middleware and the routers set the context variables; a logging filter copies them onto each record, so code
deep in the agent logs `request_id` without receiving it as an argument. Structured JSON logs come later in the course.
"""
import logging
import sys
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")
session_id_var: ContextVar[str] = ContextVar("session_id", default="-")

FORMAT = ("%(asctime)s %(levelname)s %(name)s "
          "request_id=%(request_id)s user_id=%(user_id)s session_id=%(session_id)s | %(message)s")


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        record.session_id = session_id_var.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)  # the platform (Docker, Cloud Run) collects stdout
    handler.setFormatter(logging.Formatter(FORMAT, datefmt="%H:%M:%S"))
    handler.addFilter(ContextFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("httpx", "httpx2", "httpcore", "openai"):  # one line per HTTP call to the provider: too much at INFO
        logging.getLogger(noisy).setLevel(logging.WARNING)
