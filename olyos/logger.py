#!/usr/bin/env python3
"""
OLYOS CAPITAL - Logging Module
==============================
Centralized logging configuration for Portfolio Terminal.

Provides:
- Console and file logging with different levels
- Colored console output (with fallback)
- Log rotation for file logs
- JSON format option for structured logging
- Component-specific loggers (api, backtest, screener, etc.)

Usage:
    from olyos.logger import get_logger
    log = get_logger('api')
    log.info("API request completed")
    log.debug("Response data", extra={'data': response})
"""

import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional, Union


# =============================================================================
# CONFIGURATION
# =============================================================================

# Default configuration
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_FILE = "olyos.log"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 5

# Component names for specialized loggers
COMPONENTS = [
    "api",
    "backtest",
    "screener",
    "portfolio",
    "market_data",
    "cache",
    "ui",
    "scoring",
    "position",
]

# Log level mapping
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


# =============================================================================
# ANSI COLOR CODES
# =============================================================================

class Colors:
    """ANSI color codes for console output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Text colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"

    # Background colors
    BG_RED = "\033[41m"
    BG_YELLOW = "\033[43m"


def supports_color() -> bool:
    """
    Check if the terminal supports ANSI color codes.

    Returns:
        True if colors are supported, False otherwise.
    """
    # Check for explicit environment variable
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR"):
        return True

    # Check if running in a real terminal
    if not hasattr(sys.stdout, "isatty"):
        return False
    if not sys.stdout.isatty():
        return False

    # Windows support check
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Enable ANSI support on Windows 10+
            kernel32.SetConsoleMode(
                kernel32.GetStdHandle(-11),
                7
            )
            return True
        except Exception:
            # Try colorama as fallback
            try:
                import colorama
                colorama.init()
                return True
            except ImportError:
                return False

    # Unix-like systems typically support colors
    return True


# Global color support flag
COLOR_ENABLED = supports_color()


# =============================================================================
# CUSTOM FORMATTERS
# =============================================================================

class ColoredFormatter(logging.Formatter):
    """
    Custom formatter that adds colors to console output.

    Colors are applied based on log level:
    - DEBUG: Cyan
    - INFO: Green
    - WARNING: Yellow
    - ERROR: Red
    - CRITICAL: Bold Red with background
    """

    # Level-specific color mappings
    LEVEL_COLORS = {
        logging.DEBUG: Colors.CYAN,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.BG_RED + Colors.WHITE + Colors.BOLD,
    }

    # Level name formatting (padded to 8 chars for alignment)
    LEVEL_NAMES = {
        logging.DEBUG: "DEBUG   ",
        logging.INFO: "INFO    ",
        logging.WARNING: "WARNING ",
        logging.ERROR: "ERROR   ",
        logging.CRITICAL: "CRITICAL",
    }

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        use_colors: bool = True
    ):
        """
        Initialize the colored formatter.

        Args:
            fmt: Log format string.
            datefmt: Date format string.
            use_colors: Whether to apply colors (default: True).
        """
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and COLOR_ENABLED

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record with colors.

        Args:
            record: The log record to format.

        Returns:
            Formatted log string with optional colors.
        """
        # Get color for this level
        color = self.LEVEL_COLORS.get(record.levelno, "")
        level_name = self.LEVEL_NAMES.get(record.levelno, record.levelname)

        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime(
            self.datefmt or "%Y-%m-%d %H:%M:%S"
        )

        # Build the formatted message
        if self.use_colors:
            # Colored format
            formatted = (
                f"{Colors.DIM}{timestamp}{Colors.RESET} "
                f"{color}{level_name}{Colors.RESET} "
                f"{Colors.BLUE}[{record.name}]{Colors.RESET} "
                f"{record.getMessage()}"
            )
        else:
            # Plain format
            formatted = (
                f"{timestamp} {level_name} [{record.name}] {record.getMessage()}"
            )

        # Add exception info if present
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                if self.use_colors:
                    formatted += f"\n{Colors.RED}{record.exc_text}{Colors.RESET}"
                else:
                    formatted += f"\n{record.exc_text}"

        return formatted


class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs log records as JSON objects.

    Useful for structured logging, log aggregation systems,
    and machine-readable log files.
    """

    def __init__(
        self,
        include_extra: bool = True,
        indent: Optional[int] = None
    ):
        """
        Initialize the JSON formatter.

        Args:
            include_extra: Whether to include extra fields from the record.
            indent: JSON indentation level (None for compact output).
        """
        super().__init__()
        self.include_extra = include_extra
        self.indent = indent

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record as JSON.

        Args:
            record: The log record to format.

        Returns:
            JSON-formatted log string.
        """
        # Base log data
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add location information
        log_data["location"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }

        # Add extra fields
        if self.include_extra:
            # Standard LogRecord attributes to exclude
            standard_attrs = {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "message", "asctime",
            }

            # Include any extra attributes
            extra = {
                k: v for k, v in record.__dict__.items()
                if k not in standard_attrs and not k.startswith("_")
            }
            if extra:
                log_data["extra"] = extra

        return json.dumps(log_data, indent=self.indent, default=str)


class StandardFormatter(logging.Formatter):
    """
    Standard formatter for file logging with consistent format.
    """

    DEFAULT_FORMAT = (
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
    )
    DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None
    ):
        """
        Initialize the standard formatter.

        Args:
            fmt: Log format string (default: standard format).
            datefmt: Date format string (default: ISO-like format).
        """
        super().__init__(
            fmt or self.DEFAULT_FORMAT,
            datefmt or self.DEFAULT_DATE_FORMAT
        )


# =============================================================================
# LOGGER CONFIGURATION
# =============================================================================

class LoggerConfig:
    """
    Configuration container for logger settings.
    """

    def __init__(
        self,
        level: Union[int, str] = DEFAULT_LOG_LEVEL,
        log_dir: str = DEFAULT_LOG_DIR,
        log_file: str = DEFAULT_LOG_FILE,
        max_bytes: int = DEFAULT_MAX_BYTES,
        backup_count: int = DEFAULT_BACKUP_COUNT,
        console_enabled: bool = True,
        file_enabled: bool = True,
        json_enabled: bool = False,
        json_file: str = "olyos.json.log",
        use_colors: bool = True,
    ):
        """
        Initialize logger configuration.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            log_dir: Directory for log files.
            log_file: Name of the main log file.
            max_bytes: Maximum size of log file before rotation.
            backup_count: Number of backup files to keep.
            console_enabled: Whether to log to console.
            file_enabled: Whether to log to file.
            json_enabled: Whether to create JSON log file.
            json_file: Name of the JSON log file.
            use_colors: Whether to use colors in console output.
        """
        # Convert string level to int
        if isinstance(level, str):
            level = LOG_LEVELS.get(level.upper(), DEFAULT_LOG_LEVEL)

        self.level = level
        self.log_dir = log_dir
        self.log_file = log_file
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.console_enabled = console_enabled
        self.file_enabled = file_enabled
        self.json_enabled = json_enabled
        self.json_file = json_file
        self.use_colors = use_colors


# Global configuration instance
_config: LoggerConfig = LoggerConfig()

# Track if logging has been initialized
_initialized: bool = False

# Cache of created loggers
_loggers: Dict[str, logging.Logger] = {}


# =============================================================================
# INITIALIZATION FUNCTIONS
# =============================================================================

def configure(
    level: Union[int, str] = DEFAULT_LOG_LEVEL,
    log_dir: str = DEFAULT_LOG_DIR,
    log_file: str = DEFAULT_LOG_FILE,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    console_enabled: bool = True,
    file_enabled: bool = True,
    json_enabled: bool = False,
    json_file: str = "olyos.json.log",
    use_colors: bool = True,
) -> None:
    """
    Configure the logging system.

    Should be called once at application startup before any logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_dir: Directory for log files.
        log_file: Name of the main log file.
        max_bytes: Maximum size of log file before rotation.
        backup_count: Number of backup files to keep.
        console_enabled: Whether to log to console.
        file_enabled: Whether to log to file.
        json_enabled: Whether to create JSON log file.
        json_file: Name of the JSON log file.
        use_colors: Whether to use colors in console output.

    Example:
        >>> from olyos.logger import configure, get_logger
        >>> configure(level='DEBUG', file_enabled=True)
        >>> log = get_logger('api')
        >>> log.debug("Debug message")
    """
    global _config, _initialized

    _config = LoggerConfig(
        level=level,
        log_dir=log_dir,
        log_file=log_file,
        max_bytes=max_bytes,
        backup_count=backup_count,
        console_enabled=console_enabled,
        file_enabled=file_enabled,
        json_enabled=json_enabled,
        json_file=json_file,
        use_colors=use_colors,
    )

    # Re-initialize all existing loggers with new config
    _initialized = False
    for name in list(_loggers.keys()):
        _setup_logger(name)

    _initialized = True


def _ensure_log_dir() -> str:
    """
    Ensure the log directory exists.

    Returns:
        Path to the log directory.
    """
    log_dir = _config.log_dir
    if not os.path.isabs(log_dir):
        # Make relative to the olyos package directory
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(base_dir, log_dir)

    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def _setup_logger(name: str) -> logging.Logger:
    """
    Set up a logger with the configured handlers.

    Args:
        name: Name of the logger.

    Returns:
        Configured logger instance.
    """
    # Create logger with olyos namespace
    full_name = f"olyos.{name}" if name else "olyos"
    logger = logging.getLogger(full_name)

    # Clear existing handlers
    logger.handlers.clear()

    # Set level
    logger.setLevel(_config.level)

    # Don't propagate to root logger
    logger.propagate = False

    # Add console handler
    if _config.console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(_config.level)
        console_handler.setFormatter(
            ColoredFormatter(use_colors=_config.use_colors)
        )
        logger.addHandler(console_handler)

    # Add file handler
    if _config.file_enabled:
        log_dir = _ensure_log_dir()
        log_path = os.path.join(log_dir, _config.log_file)

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=_config.max_bytes,
            backupCount=_config.backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(_config.level)
        file_handler.setFormatter(StandardFormatter())
        logger.addHandler(file_handler)

    # Add JSON file handler
    if _config.json_enabled:
        log_dir = _ensure_log_dir()
        json_path = os.path.join(log_dir, _config.json_file)

        json_handler = RotatingFileHandler(
            json_path,
            maxBytes=_config.max_bytes,
            backupCount=_config.backup_count,
            encoding="utf-8",
        )
        json_handler.setLevel(_config.level)
        json_handler.setFormatter(JSONFormatter())
        logger.addHandler(json_handler)

    return logger


# =============================================================================
# PUBLIC API
# =============================================================================

def get_logger(name: str = "") -> logging.Logger:
    """
    Get a logger for a specific component.

    Creates the logger if it doesn't exist, reuses existing loggers.

    Args:
        name: Component name (e.g., 'api', 'backtest', 'screener').
              Empty string returns the root olyos logger.

    Returns:
        Configured logger instance.

    Example:
        >>> from olyos.logger import get_logger
        >>> log = get_logger('api')
        >>> log.info("API initialized")
        >>> log.debug("Request details", extra={'url': '/api/data'})
        >>> log.error("Request failed", exc_info=True)
    """
    if name not in _loggers:
        _loggers[name] = _setup_logger(name)
    return _loggers[name]


def set_level(level: Union[int, str], logger_name: Optional[str] = None) -> None:
    """
    Set the log level for a specific logger or all loggers.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        logger_name: Specific logger name, or None for all loggers.

    Example:
        >>> set_level('DEBUG')  # Set all loggers to DEBUG
        >>> set_level('ERROR', 'api')  # Set only 'api' logger to ERROR
    """
    if isinstance(level, str):
        level = LOG_LEVELS.get(level.upper(), DEFAULT_LOG_LEVEL)

    if logger_name is not None:
        if logger_name in _loggers:
            _loggers[logger_name].setLevel(level)
            for handler in _loggers[logger_name].handlers:
                handler.setLevel(level)
    else:
        _config.level = level
        for logger in _loggers.values():
            logger.setLevel(level)
            for handler in logger.handlers:
                handler.setLevel(level)


def enable_debug() -> None:
    """
    Enable DEBUG level for all loggers.

    Convenience function for development/troubleshooting.
    """
    set_level(logging.DEBUG)


def disable_console() -> None:
    """
    Disable console output for all loggers.

    Useful for production environments or testing.
    """
    for logger in _loggers.values():
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.StreamHandler) and \
               not isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)


def get_log_file_path() -> Optional[str]:
    """
    Get the path to the current log file.

    Returns:
        Path to the log file, or None if file logging is disabled.
    """
    if not _config.file_enabled:
        return None
    log_dir = _ensure_log_dir()
    return os.path.join(log_dir, _config.log_file)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def log_api(message: str, level: str = "INFO", **kwargs) -> None:
    """
    Log an API-related message.

    Args:
        message: Log message.
        level: Log level (default: INFO).
        **kwargs: Extra fields to include in the log.
    """
    logger = get_logger("api")
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message, extra=kwargs if kwargs else None)


def log_backtest(message: str, level: str = "INFO", **kwargs) -> None:
    """
    Log a backtest-related message.

    Args:
        message: Log message.
        level: Log level (default: INFO).
        **kwargs: Extra fields to include in the log.
    """
    logger = get_logger("backtest")
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message, extra=kwargs if kwargs else None)


def log_screener(message: str, level: str = "INFO", **kwargs) -> None:
    """
    Log a screener-related message.

    Args:
        message: Log message.
        level: Log level (default: INFO).
        **kwargs: Extra fields to include in the log.
    """
    logger = get_logger("screener")
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message, extra=kwargs if kwargs else None)


def log_portfolio(message: str, level: str = "INFO", **kwargs) -> None:
    """
    Log a portfolio-related message.

    Args:
        message: Log message.
        level: Log level (default: INFO).
        **kwargs: Extra fields to include in the log.
    """
    logger = get_logger("portfolio")
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message, extra=kwargs if kwargs else None)


# =============================================================================
# CONTEXT MANAGER FOR TEMPORARY LOG LEVEL
# =============================================================================

class temporary_log_level:
    """
    Context manager for temporarily changing the log level.

    Example:
        >>> with temporary_log_level('DEBUG'):
        ...     log.debug("This will be logged")
        >>> log.debug("This might not be logged")
    """

    def __init__(
        self,
        level: Union[int, str],
        logger_name: Optional[str] = None
    ):
        """
        Initialize the context manager.

        Args:
            level: Temporary log level.
            logger_name: Specific logger, or None for all.
        """
        if isinstance(level, str):
            level = LOG_LEVELS.get(level.upper(), DEFAULT_LOG_LEVEL)

        self.level = level
        self.logger_name = logger_name
        self.previous_levels: Dict[str, int] = {}

    def __enter__(self):
        """Save current levels and set temporary level."""
        if self.logger_name is not None:
            if self.logger_name in _loggers:
                logger = _loggers[self.logger_name]
                self.previous_levels[self.logger_name] = logger.level
                logger.setLevel(self.level)
        else:
            for name, logger in _loggers.items():
                self.previous_levels[name] = logger.level
                logger.setLevel(self.level)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore previous log levels."""
        for name, level in self.previous_levels.items():
            if name in _loggers:
                _loggers[name].setLevel(level)
        return False


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

# Create default root logger on import
_root_logger = get_logger("")


# Expose standard log levels for convenience
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL


if __name__ == "__main__":
    # Demo usage
    configure(level="DEBUG", console_enabled=True, file_enabled=False)

    log = get_logger("demo")
    log.debug("This is a debug message")
    log.info("This is an info message")
    log.warning("This is a warning message")
    log.error("This is an error message")
    log.critical("This is a critical message")

    # Test component loggers
    api_log = get_logger("api")
    api_log.info("API logger test")

    backtest_log = get_logger("backtest")
    backtest_log.info("Backtest logger test")

    # Test exception logging
    try:
        raise ValueError("Test exception")
    except ValueError:
        log.error("Caught an exception", exc_info=True)

    # Test temporary log level
    set_level("WARNING")
    log.info("This should not appear")

    with temporary_log_level("DEBUG"):
        log.debug("This should appear (temporary DEBUG)")

    log.debug("This should not appear again")
