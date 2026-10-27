"""Structured logging module with automatic PII masking for phone numbers."""

import logging
import re
import sys

# Regex pattern for international and standard phone numbers (e.g. +91 9876543210 or 9876543210)
PHONE_REGEX = re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")


def mask_phone_number(phone: str | None) -> str:
    """Masks a phone number to protect caller privacy.

    Example:
        '+919876543210' -> '+9198*****210'
        '9876543210'    -> '98*****210'
    """
    if not phone:
        return ""
    has_plus = phone.startswith("+")
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7:
        return "***"

    # If it had a +, first 4 digits are prefix (e.g. 9198), last 3 are suffix
    if has_plus and len(digits) >= 8:
        prefix = f"+{digits[:4]}"
        suffix = digits[-3:]
        stars = "*" * (len(digits) - 7)
        return f"{prefix}{stars}{suffix}"
    else:
        prefix = digits[:2]
        suffix = digits[-3:]
        stars = "*" * (len(digits) - 5)
        return f"{prefix}{stars}{suffix}"



class PIIMaskingFormatter(logging.Formatter):
    """Custom logging formatter that scrubs sensitive PII (phone numbers) from log messages."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        # Search and mask phone occurrences in log output
        def repl(match: re.Match[str]) -> str:
            raw = match.group(0)
            return mask_phone_number(raw)

        return PHONE_REGEX.sub(repl, original)


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Creates or retrieves a configured logger with PII masking."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = PIIMaskingFormatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        logger.propagate = False
    return logger


# Default application logger instance
logger = get_logger("voice_agent")
