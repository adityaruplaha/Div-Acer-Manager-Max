"""The daemon's lifecycle and command line"""

import argparse
import configparser
import io
import logging
import os
import signal
import sys
import traceback

from . import VERSION, paths
from .files import atomic_write
from .logs import log, setup_logging
from .manager import DAMXManager
from .power_source import PowerSourceDetector
from .server import DaemonServer
# from .keyboard_monitor import KeyboardMonitor


class DAMXDaemon:
    """Main daemon class that manages the lifecycle"""

    def __init__(self, verbose: bool = False):
        self.running = False
        self.manager = None
        self.server = None
        self.config = None
        # --verbose/--debug force debug logging over the configured level
        self.verbose = verbose

    def load_config(self):
        """Load configuration from file"""
        config = configparser.ConfigParser()

        # Create default config if it doesn't exist
        if not os.path.exists(paths.CONFIG_PATH):
            log.info(f"Creating default config at {paths.CONFIG_PATH}")
            config['General'] = {
                'LogLevel': 'INFO',
                'AutoDetectFeatures': 'True'
            }

            # Write default config
            buffer = io.StringIO()
            config.write(buffer)
            atomic_write(paths.CONFIG_PATH, buffer.getvalue())
        else:
            # Load existing config
            config.read(paths.CONFIG_PATH)

        self.config = config

        # Set log level from config
        if self.verbose:
            log.setLevel(logging.DEBUG)
        elif 'General' in config and 'LogLevel' in config['General']:
            log_level = config['General']['LogLevel'].upper()
            if log_level in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
                log.setLevel(getattr(logging, log_level))
                log.info(f"Log level set to {log_level}")
            else:
                log.warning(f"Unknown LogLevel {log_level!r} in {paths.CONFIG_PATH}, keeping {logging.getLevelName(log.level)}")

        return config

    def setup(self):
        """Set up the daemon"""
        # Load configuration first
        self.load_config()

        try:
            # Initialize DAMXManager
            self.manager = DAMXManager()
            log.info(f"Driver Version: {self.manager.get_driver_version()}")

            # Initialize keyboard monitor early
            # self.keyboard_monitor = KeyboardMonitor(
            #     target_keycode=425, 
            #     command_to_run="DAMX",  # Updated command
            #     logger=log
            # )
            # kb_success = self.keyboard_monitor.start_monitoring()
            
            # if not kb_success:
            #     log.error("Failed to start keyboard monitoring")
            #     # Don't return False here - continue with reduced functionality

            # Initialize power monitor (started in run())
            self.power_monitor = PowerSourceDetector(self.manager)

            # Log detected features
            features_str = ", ".join(sorted(self.manager.available_features))
            log.info(f"Detected features: {features_str}")

            return True
        except Exception as e:
            log.error(f"Failed to set up daemon: {e}")
            log.error(traceback.format_exc())
            return False
    


    def run(self):
        """Run the daemon"""
        # Write PID file
        with open(paths.PID_FILE, 'w') as f:
            f.write(str(os.getpid()))

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

        # if self.keyboard_monitor:
        #     success = self.keyboard_monitor.start_monitoring()
        #     if success:
        #         log.info("Keyboard monitoring started successfully")
        #     else:
        #         log.warning("Failed to start keyboard monitoring")

        # Set up and run the server
        try:
            self.running = True
            self.server = DaemonServer(self.manager)
            self.power_monitor.start_monitoring()
            self.server.start()
            # Start keyboard monitoring
            
        except Exception as e:
            log.error(f"Error running daemon: {e}")
            log.error(traceback.format_exc())
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        log.info("Cleaning up resources...")
    
        # Stop server and clean up socket
        if self.server:
            self.server.stop()
            self.server.cleanup_socket()  # Additional cleanup
            # Stop keyboard monitoring
        # if hasattr(self, 'keyboard_monitor') and self.keyboard_monitor:
        #     self.keyboard_monitor.stop_monitoring()
        #     log.info("Keyboard monitoring stopped")
    
        if self.power_monitor:
            self.power_monitor.stop_monitoring()
    
        # Remove PID file
        try:
            if os.path.exists(paths.PID_FILE):
                os.unlink(paths.PID_FILE)
        except OSError:
            pass
    
        log.info("Daemon stopped")

    def signal_handler(self, sig, frame):
        """Handle termination signals"""
        log.info(f"Received signal {sig}, shutting down...")
        self.running = False
        if self.server:
            self.server.running = False

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="DAMX-Daemon")
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose logging")
    parser.add_argument('--version', action='version', version=f"DAMX-Daemon v{VERSION}")
    parser.add_argument('--debug', action='store_true', help="Enable debug logging (same as --verbose)")
    parser.add_argument('--config', type=str, help=f"Path to config file (default: {paths.CONFIG_PATH})")
    return parser.parse_args()

def main():
    """Main function"""
    args = parse_args()

    # Check if running as root
    if os.geteuid() != 0:
        print("This daemon must run as root. Please use sudo or run as root.")
        sys.exit(1)

    setup_logging()

    # Set log level based on verbosity
    verbose = args.verbose or args.debug
    if verbose:
        log.setLevel(logging.DEBUG)
        log.debug("Debug logging enabled")

    # Use custom config path if provided
    if args.config:
        paths.CONFIG_PATH = args.config

    daemon = DAMXDaemon(verbose=verbose)
    if daemon.setup():
        daemon.run()
    else:
        log.error("Failed to set up daemon, exiting...")
        sys.exit(1)
