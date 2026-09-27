"""The daemon's logger"""

import logging
import logging.handlers

from . import paths

log = logging.getLogger("DAMXDaemon")


def setup_logging():
    """Log to the console and to a rotating file"""
    log.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    log.addHandler(console_handler)

    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        paths.LOG_PATH, maxBytes=1024*1024*5, backupCount=5)
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)
