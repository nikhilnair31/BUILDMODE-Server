import time, logging
from functools import wraps

logger = logging.getLogger(__name__)

def timed_route(label=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                route_name = label or func.__name__
                logger.info(f"[TIMER] {route_name} took {duration:.4f} seconds")
        return wrapper
    return decorator
