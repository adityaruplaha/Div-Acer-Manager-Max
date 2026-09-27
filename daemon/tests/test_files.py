import os
import stat

from damx_daemon.files import atomic_write


def test_atomic_write_creates_and_replaces(tmp_path):
    path = tmp_path / "modprobe.d" / "damx.conf"
    atomic_write(str(path), "first\n")
    assert path.read_text() == "first\n"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o644

    atomic_write(str(path), "second\n")
    assert path.read_text() == "second\n"
    assert os.listdir(path.parent) == ["damx.conf"]
