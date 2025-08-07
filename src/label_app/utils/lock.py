import functools
import threading


def lock(thread_lock: threading.Lock):
    def deco(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            with thread_lock:
                return f(*args, **kwargs)
        return inner
    return deco

