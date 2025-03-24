from collections.abc import Callable
from functools import wraps
from common.tracing import get_tracer
from opentelemetry.trace import SpanKind, StatusCode


def trace_func(service: str):
    def decorate(func: Callable) -> Callable:
        tracer = get_tracer(service)

        @wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(func.__name__, kind=SpanKind.SERVER) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(StatusCode.ERROR, description=f"{type(e).__name__}: {e}")
                    raise

        return wrapper

    return decorate
