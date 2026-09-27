"""The daemon's logger

The daemon logs to stderr, which systemd connects to the journal. There
each line carries its priority as an sd-daemon(3) prefix, which journald
reads and strips, and no timestamp, since the journal records its own.
Run by hand, it logs ordinary timestamped lines.
"""

import logging
import os
import sys

log = logging.getLogger("DAMXDaemon")


def stderr_is_journal() -> bool:
    """Whether stderr is connected to the journal, checked as systemd.exec(5) describes"""
    stream = os.environ.get("JOURNAL_STREAM")
    if not stream:
        return False
    try:
        device, inode = (int(n) for n in stream.split(":"))
        stat = os.fstat(sys.stderr.fileno())
    except (ValueError, OSError):
        return False
    return (stat.st_dev, stat.st_ino) == (device, inode)


def priority(level: int) -> int:
    """The syslog priority for a logging level"""
    if level >= logging.CRITICAL:
        return 2
    if level >= logging.ERROR:
        return 3
    if level >= logging.WARNING:
        return 4
    if level >= logging.INFO:
        return 6
    return 7


class JournalFormatter(logging.Formatter):
    """Prefixes every line of a record, tracebacks included, with its priority"""

    def format(self, record: logging.LogRecord) -> str:
        prefix = f"<{priority(record.levelno)}>"
        return "\n".join(prefix + line for line in super().format(record).splitlines())


def setup_logging():
    """Log to stderr, for the journal when systemd runs the daemon"""
    log.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    if stderr_is_journal():
        handler.setFormatter(JournalFormatter('%(message)s'))
    else:
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    log.addHandler(handler)
