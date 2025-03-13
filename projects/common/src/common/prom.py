import time

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
from starlette.types import ASGIApp

from common.tracing import get_tracer

_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    1.5,
    2.0,
    2.5,
    3.0,
    3.5,
    4.0,
    4.5,
    5.0,
    5.5,
    6.0,
    6.5,
    7.0,
    7.5,
    10.0,
    float("inf"),
)

INFO = Gauge("service", "App Name", labelnames=["service"])
INVOCATIONS = Counter(
    "function_invocations",
    "Counting the number of function invocations",
    labelnames=["service", "function"],
)
INVOCATION_RESPONSES = Counter(
    "function_invocation_responses",
    "Counting the number of function invocations",
    labelnames=["service", "function"],
)

INVOCATIONS_PROCESSING_TIME = Histogram(
    "function_invocation_time",
    "Histogram of function invocation processing time by path (in seconds)",
    labelnames=["service", "function"],
    buckets=_BUCKETS,
)
BASE_EXCEPTIONS = Counter(
    "base_exceptions",
    "Total count of exceptions raised by function and exception type",
    labelnames=["service", "function", "exception_type"],
)
NOTIFY_EXCEPTIONS = Counter(
    "notify_exceptions",
    "Total count of non-critical exceptions raised by function and exception type",
    labelnames=["service", "function", "exception_type"],
)
CRITICAL_EXCEPTIONS = Counter(
    "critical_exceptions",
    "Total count of critical exceptions raised by function and exception type",
    labelnames=["service", "function", "exception_type"],
)
INVOCATIONS_IN_PROGRESS = Gauge(
    "function_invocations_in_progress",
    "Gauge of function invocations currently being processed",
    labelnames=["service", "function"],
)
ACCUMULATED_EXCEPTIONS = Gauge(
    "accumulated_exceptions",
    "Number of errors in the configured time period. Will be negative if no issue. Zero or greater for errors.",
    labelnames=["service", "function"],
)
LOG_TOTAL = Counter(
    "log_total",
    "Total number of log messages",
    labelnames=["service", "level"],
)


def reset_metrics(service: str) -> None:
    INVOCATIONS._metrics.clear()
    INVOCATION_RESPONSES._metrics.clear()
    INVOCATIONS_PROCESSING_TIME._metrics.clear()
    BASE_EXCEPTIONS._metrics.clear()
    NOTIFY_EXCEPTIONS._metrics.clear()
    CRITICAL_EXCEPTIONS._metrics.clear()
    INVOCATIONS_IN_PROGRESS._metrics.clear()
    ACCUMULATED_EXCEPTIONS._metrics.clear()
    LOG_TOTAL._metrics.clear()
    BASE_EXCEPTIONS.labels(service=service, function="", exception_type="").inc(0)
    NOTIFY_EXCEPTIONS.labels(service=service, function="", exception_type="").inc(0)
    CRITICAL_EXCEPTIONS.labels(service=service, function="", exception_type="").inc(0)


class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, service: str, intercept_exceptions: bool = True) -> None:
        super().__init__(app)
        self.service = service
        INFO.labels(service=self.service).inc()
        self.propagator = TraceContextTextMapPropagator()
        self.tracer = get_tracer(service)
        self.intercept_exceptions = intercept_exceptions

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        path, is_handled_path = self.get_path(request)
        function = f"{method} {path}"

        if not is_handled_path:
            return await call_next(request)

        context = self.propagator.extract(request.headers)
        with self.tracer.start_as_current_span(function, context=context, kind=SpanKind.SERVER) as span:
            INVOCATIONS_IN_PROGRESS.labels(function=function, service=self.service).inc()
            INVOCATIONS.labels(function=function, service=self.service).inc()
            before_time = time.perf_counter()
            try:
                response = await call_next(request)
                if span is not None:
                    span.set_status(StatusCode.OK)
            except Exception as e:
                if span is not None:
                    span.record_exception(e)
                    span.set_status(StatusCode.ERROR, description=f"{type(e).__name__}: {e}")
                BASE_EXCEPTIONS.labels(
                    function=function,
                    exception_type=type(e).__name__,
                    service=self.service,
                ).inc()

                # If we let the ASGI server handle the exception, we won't get the trace id emitted
                # So instead, we optionally intercept non-HTTP exceptions, log them, and then
                # set the response to an appropriate JSONResponse
                if self.intercept_exceptions and not isinstance(e, HTTPException):
                    logger.opt(exception=e).exception(f"Exception in {function}: {e}")
                    response = JSONResponse(status_code=500, content={"detail": str(e)})
                else:
                    raise
            else:
                after_time = time.perf_counter()
                INVOCATION_RESPONSES.labels(
                    function=function,
                    service=self.service,
                ).inc()
                INVOCATIONS_PROCESSING_TIME.labels(service=self.service, function=function).observe(
                    after_time - before_time
                )
            finally:
                INVOCATIONS_IN_PROGRESS.labels(function=function, service=self.service).dec()

            return response

    @staticmethod
    def get_path(request: Request) -> tuple[str, bool]:
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                return route.path, True

        return request.url.path, False


def metrics(request: Request) -> Response:
    return Response(generate_latest(REGISTRY), headers={"Content-Type": CONTENT_TYPE_LATEST})
