"""
CRON Expression Parsing and Utilities
Provides validation, next run calculation, and human-readable descriptions for CRON expressions
"""

import logging
from datetime import datetime

from croniter import croniter

logger = logging.getLogger(__name__)


def validate_cron_expression(expression: str) -> bool:
    """
    Validate CRON expression syntax.

    Only accepts standard 5-field CRON expressions (minute hour day month dayofweek).
    Rejects extended 6-field expressions with seconds.

    Args:
        expression: CRON expression string (e.g., "0 9 * * *", "*/30 * * * *")

    Returns:
        True if valid 5-field CRON, False otherwise
    """
    try:
        # First check field count - only accept 5-field CRON
        parts = expression.split()
        if len(parts) != 5:
            logger.warning(f"Invalid CRON expression '{expression}': must have exactly 5 fields, got {len(parts)}")
            return False

        # Then check croniter validation
        return croniter.is_valid(expression)
    except Exception as e:
        logger.warning(f"Error validating CRON expression '{expression}': {e}")
        return False


def is_cron_expression_valid(expression: str) -> bool:
    """
    Comprehensive CRON expression validation.

    Checks both croniter validation AND that the expression can be parsed
    into a human-readable format. This catches malformed expressions that
    croniter might accept but can't actually be scheduled.

    Args:
        expression: CRON expression string

    Returns:
        True if valid and parseable, False otherwise
    """
    # First check croniter validation
    if not validate_cron_expression(expression):
        return False

    # Then check if it can be parsed to human-readable
    # If it returns an "Invalid" message, it's malformed
    human_readable = cron_to_human_readable(expression)
    if human_readable in ("Invalid CRON expression format", "Invalid CRON expression"):
        return False

    return True


def round_to_next_timer_interval(dt: datetime) -> datetime:
    """
    Round a datetime up to the next 5-minute timer interval.

    Our schedule processor runs every 5 minutes (at :00, :05, :10, :15, etc.),
    so we round up the actual CRON next run to the next timer execution.

    Args:
        dt: Datetime to round

    Returns:
        Datetime rounded up to next 5-minute interval

    Examples:
        10:11 -> 10:15
        10:15 -> 10:15 (already on interval)
        10:16 -> 10:20
    """
    from datetime import timedelta

    # Get minutes since midnight
    minutes_since_midnight = dt.hour * 60 + dt.minute

    # Round up to next 5-minute interval
    rounded_minutes = ((minutes_since_midnight + 4) // 5) * 5

    # If we've rolled over to next day
    if rounded_minutes >= 1440:  # 24 * 60
        rounded_minutes = 0
        dt = dt + timedelta(days=1)

    # Set the new time
    new_hour = rounded_minutes // 60
    new_minute = rounded_minutes % 60

    return dt.replace(hour=new_hour, minute=new_minute, second=0, microsecond=0)


def calculate_next_run(expression: str, from_time: datetime | None = None) -> datetime:
    """
    Calculate the next run time for a CRON expression.

    Since our schedule processor runs every 5 minutes, the returned time
    is rounded up to the next 5-minute timer interval (:00, :05, :10, etc.).

    Args:
        expression: CRON expression string
        from_time: Base time to calculate from (default: now in UTC)

    Returns:
        datetime of next scheduled run in UTC, rounded to next 5-minute interval

    Raises:
        ValueError: If CRON expression is invalid
    """
    if not validate_cron_expression(expression):
        raise ValueError(f"Invalid CRON expression: {expression}")

    # Use provided time or current UTC time
    base_time = from_time or datetime.utcnow()

    # Create croniter instance and get next run
    cron = croniter(expression, base_time)
    next_run = cron.get_next(datetime)

    # Round up to next 5-minute timer interval
    # This ensures Next Run reflects when it will ACTUALLY execute
    next_run_rounded = round_to_next_timer_interval(next_run)

    return next_run_rounded


def cron_to_human_readable(expression: str) -> str:
    """
    Convert CRON expression to human-readable description.

    Examples:
        "0 9 * * *" -> "Every day at 09:00"
        "0 */5 * * * *" -> "Every 5 minutes"
        "0 0 * * 0" -> "Every Sunday at 00:00"
        "0 0 1 * *" -> "On the 1st of every month at 00:00"

    Args:
        expression: CRON expression string

    Returns:
        Human-readable description
    """
    if not validate_cron_expression(expression):
        return "Invalid CRON expression"

    try:
        parts = expression.split()

        # Only accept standard 5-field CRON (minute hour day month dayofweek)
        if len(parts) != 5:
            return "Invalid CRON expression format"

        minute, hour, day, month, dayofweek = parts

        # Build description based on patterns

        # Check if it's every N minutes (must check BEFORE every minute)
        if minute.startswith("*/") and hour == "*" and day == "*" and month == "*" and dayofweek == "*":
            interval = minute.split("/")[1]
            return f"Every {interval} minutes"

        # Check if it's every minute
        if minute == "*" and hour == "*" and day == "*" and month == "*" and dayofweek == "*":
            return "Every minute"

        # Check if it's every hour
        if minute == "0" and hour == "*" and day == "*" and month == "*" and dayofweek == "*":
            return "Every hour at minute 0"

        # Check if it's every N hours
        if minute == "0" and hour.startswith("*/") and day == "*" and month == "*" and dayofweek == "*":
            interval = hour.split("/")[1]
            return f"Every {interval} hours"

        # Build time part
        time_part = ""
        if minute == "0" and hour != "*":
            if "," in hour:
                times = hour.split(",")
                time_part = f"at {', '.join([f'{h:0>2}:00' for h in times])}"
            elif "-" in hour:
                start, end = hour.split("-")
                time_part = f"between {start:0>2}:00 and {end:0>2}:00"
            elif hour.startswith("*/"):
                interval = hour.split("/")[1]
                time_part = f"every {interval} hours"
            else:
                time_part = f"at {hour:0>2}:00"
        elif minute != "*" and hour != "*":
            time_part = f"at {hour:0>2}:{minute:0>2}"

        # Build frequency part
        if day == "*" and month == "*" and dayofweek == "*":
            frequency = "every day"
        elif dayofweek == "0" or dayofweek == "7":
            frequency = "every Sunday"
        elif dayofweek == "1":
            frequency = "every Monday"
        elif dayofweek == "2":
            frequency = "every Tuesday"
        elif dayofweek == "3":
            frequency = "every Wednesday"
        elif dayofweek == "4":
            frequency = "every Thursday"
        elif dayofweek == "5":
            frequency = "every Friday"
        elif dayofweek == "6":
            frequency = "every Saturday"
        elif day == "1" and month == "*":
            frequency = "on the 1st of every month"
        elif day != "*" and month != "*":
            frequency = f"on day {day} of month {month}"
        elif day != "*":
            frequency = f"on day {day} of every month"
        else:
            frequency = "daily"

        # Combine parts
        if time_part:
            return f"{frequency} {time_part}".replace("  ", " ")
        else:
            return frequency

    except Exception as e:
        logger.warning(f"Error converting CRON to human readable: {e}")
        return f"CRON: {expression}"
