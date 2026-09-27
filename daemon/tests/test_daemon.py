import logging

from damx_daemon import paths
from damx_daemon.daemon import DAMXDaemon
from damx_daemon.logs import log


def test_default_config_is_written_and_its_log_level_applied(fake_system):
    DAMXDaemon().load_config()
    with open(paths.CONFIG_PATH) as f:
        assert "loglevel = INFO" in f.read()
    assert log.level == logging.INFO


def test_configured_log_level_is_honoured(fake_system):
    DAMXDaemon().load_config()
    with open(paths.CONFIG_PATH, "w") as f:
        f.write("[General]\nLogLevel = WARNING\n")
    DAMXDaemon().load_config()
    assert log.level == logging.WARNING


def test_verbose_overrides_the_configured_level(fake_system):
    DAMXDaemon(verbose=True).load_config()
    assert log.level == logging.DEBUG
