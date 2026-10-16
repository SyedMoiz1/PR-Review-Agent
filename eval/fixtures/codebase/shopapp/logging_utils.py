import logging

SENSITIVE_FIELDS = {"password", "token", "card_number", "secret"}


def get_logger(name: str) -> logging.Logger:
    """All modules log through this helper instead of print()."""
    logger = logging.getLogger(f"shopapp.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def redact(data: dict) -> dict:
    """Return a copy of data that is safe to log: sensitive fields are masked."""
    return {k: ("***" if k in SENSITIVE_FIELDS else v) for k, v in data.items()}
