import logging
import sys


def get_logger(name: str = "frida-launcher") -> logging.Logger:
    """Returns a configured logger that outputs to stderr with [frida-launcher] prefix."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("[%(name)s] %(levelname)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


# Module-level convenience logger
log = get_logger()
