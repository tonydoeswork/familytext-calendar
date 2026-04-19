import functools
import logging
import time

logger = logging.getLogger(__name__)


def retry(max_attempts: int = 3, backoff_seconds: tuple = (5, 15, 45)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_attempts - 1:
                        wait = backoff_seconds[min(attempt, len(backoff_seconds) - 1)]
                        logger.warning(
                            f"attempt_number={attempt + 1} error_message={exc} "
                            f"retrying {func.__name__} in {wait}s"
                        )
                        time.sleep(wait)
                    else:
                        logger.warning(
                            f"attempt_number={attempt + 1} error_message={exc} "
                            f"all {max_attempts} attempts exhausted for {func.__name__}"
                        )
            raise last_exc
        return wrapper
    return decorator
