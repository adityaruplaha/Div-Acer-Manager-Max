import logging
import os
import sys

from damx_daemon.logs import JournalFormatter, stderr_is_journal


def record(level, message, exc_info=None):
    return logging.LogRecord("DAMXDaemon", level, __file__, 1, message, None, exc_info)


def test_stderr_is_not_the_journal_without_journal_stream(monkeypatch):
    monkeypatch.delenv("JOURNAL_STREAM", raising=False)
    assert not stderr_is_journal()


def test_stderr_is_the_journal_when_journal_stream_names_it(tmp_path, monkeypatch):
    with open(tmp_path / "stderr", "w") as stderr:
        monkeypatch.setattr(sys, "stderr", stderr)
        stat = os.fstat(stderr.fileno())
        monkeypatch.setenv("JOURNAL_STREAM", f"{stat.st_dev}:{stat.st_ino}")
        assert stderr_is_journal()
        # A service's child that inherits the variable but not the stream
        monkeypatch.setenv("JOURNAL_STREAM", f"{stat.st_dev}:{stat.st_ino + 1}")
        assert not stderr_is_journal()


def test_journal_lines_carry_their_priority():
    formatter = JournalFormatter("%(message)s")
    assert formatter.format(record(logging.DEBUG, "debug")) == "<7>debug"
    assert formatter.format(record(logging.INFO, "info")) == "<6>info"
    assert formatter.format(record(logging.WARNING, "warning")) == "<4>warning"
    assert formatter.format(record(logging.ERROR, "error")) == "<3>error"
    assert formatter.format(record(logging.CRITICAL, "critical")) == "<2>critical"


def test_every_line_of_a_traceback_is_prefixed():
    try:
        raise ValueError("boom")
    except ValueError:
        exc_info = sys.exc_info()
    lines = JournalFormatter("%(message)s").format(record(logging.ERROR, "failed", exc_info)).splitlines()
    assert len(lines) > 2
    assert all(line.startswith("<3>") for line in lines)
