from collections.abc import Callable
from datetime import timedelta
from functools import wraps
from common.log import configure_logging
from common.tracing import get_tracer
from opentelemetry.trace import SpanKind, StatusCode
from common.settings import settings
from prefect import flow, task, Flow
from prefect.runtime.flow_run import get_flow_name

from prefect.client.schemas.objects import FlowRun, State, StateType


from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    push_to_gateway,
)

flow_registry = CollectorRegistry()

_BUCKETS = (
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
    4.0,
    8.0,
    15.0,
    30.0,
    60.0,
    120.0,
    300.0,
    600.0,
    1800.0,
    3600.0,
    7200.0,
    float("inf"),
)

FLOW_INVOCATIONS = Counter(
    "flow_invocations",
    "Counting the number of function invocations",
    labelnames=["flow"],
    registry=flow_registry,
)

FLOW_PROCESSING_TIME = Histogram(
    "flow_processing_time",
    "Histogram of function invocation processing time by path (in seconds)",
    labelnames=["flow"],
    buckets=_BUCKETS,
    registry=flow_registry,
)
FLOW_STATUS = Counter(
    "flow_status",
    "Counting the success/failures of flows",
    labelnames=["flow", "status"],
    registry=flow_registry,
)
FLOWS_IN_PROGRESS = Gauge(
    "flows_in_progress",
    "Gauge of flows currently being processed",
    labelnames=["flow"],
    registry=flow_registry,
)


def push_metrics() -> None:
    push_to_gateway(settings.push_gateway, job=settings.service, registry=flow_registry)


def record_ending(name: str, status: str, duration: timedelta) -> None:
    FLOW_STATUS.labels(name, status).inc()
    FLOWS_IN_PROGRESS.labels(name).dec()
    FLOW_PROCESSING_TIME.labels(name).observe(duration.total_seconds())
    push_metrics()


def on_finish(flow: Flow, flow_run: FlowRun, state: State):
    record_ending(flow.name, state.type.value, flow_run.total_run_time)


def on_error(flow: Flow, flow_run: FlowRun, state: State):
    record_ending(flow.name, state.type.value, flow_run.total_run_time)


TASK_DEFAULT_KWARGS = {
    "retries": 2,
    "retry_delay_seconds": 10,
    "log_prints": True,
    "timeout_seconds": 3600,  # An hour timeout per task
    "cache_result_in_memory": False,
}


FLOW_DEFAULT_KWARGS = {
    "timeout_seconds": 3600 * 24 * 7,  # A week timeout per flow
    "on_crashed": [on_error],
    "on_failure": [on_error],
    "on_completion": [on_finish],
    "log_prints": True,
    "cache_result_in_memory": False,
}


def data_task(**kwargs):
    def decorate(func: Callable) -> Callable:
        tracer = get_tracer(settings.service)
        final_kwargs = {**TASK_DEFAULT_KWARGS, **kwargs}

        @task(**final_kwargs)
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


def data_flow(**kwargs):
    def decorate(func: Callable) -> Callable:
        tracer = get_tracer(settings.service)
        final_kwargs = {**FLOW_DEFAULT_KWARGS, **kwargs}

        @flow(**final_kwargs)
        @wraps(func)
        def wrapper(*args, **kwargs):
            configure_logging(settings.service)
            name = get_flow_name()
            if name is None:
                name = func.__name__
            with tracer.start_as_current_span(name, kind=SpanKind.SERVER) as span:
                try:
                    FLOW_INVOCATIONS.labels(name).inc()
                    FLOWS_IN_PROGRESS.labels(name).inc()
                    push_metrics()
                    result = func(*args, **kwargs)
                    # Note because flows can crash, we don't handle the post-execution
                    # prometheus here
                    if isinstance(result, State):
                        if result.type != StateType.COMPLETED:
                            span.set_status(StatusCode.OK)
                        else:
                            span.set_status(StatusCode.ERROR, description=result.message)
                    else:
                        span.set_status(StatusCode.OK)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(StatusCode.ERROR, description=f"{type(e).__name__}: {e}")
                    raise

        return wrapper

    return decorate
