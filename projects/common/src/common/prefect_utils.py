from collections.abc import Callable
from functools import wraps
import time
from common.log import configure_logging
from common.tracing import get_tracer
from opentelemetry.trace import SpanKind, StatusCode
from common.settings import settings
from prefect import flow, task, Flow
from prefect.runtime.flow_run import get_flow_name

from prefect.client.schemas.objects import FlowRun, State, StateType


from prometheus_client import CollectorRegistry, Counter, Histogram, push_to_gateway

initial_registry = CollectorRegistry()
interim_registry = CollectorRegistry()
final_registry = CollectorRegistry()

_BUCKETS = (
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.0,
    3.0,
    4.0,
    5.0,
    6.0,
    7.0,
    8.0,
    9.0,
    10.0,
    15.0,
    20.0,
    25.0,
    30.0,
    45.0,
    60.0,
    90.0,
    120.0,
    180.0,
    240.0,
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
    registry=initial_registry,
)

FLOW_PROCESSING_TIME = Histogram(
    "flow_processing_time",
    "Histogram of function invocation processing time by path (in seconds)",
    labelnames=["flow"],
    buckets=_BUCKETS,
    registry=interim_registry,
)
FLOW_STATUS = Counter(
    "flow_status",
    "Counting the success/failures of flows",
    labelnames=["flow", "status"],
    registry=final_registry,
)
FLOWS_FINISHED = Counter(
    "flows_finished",
    "Gauge of flows currently being processed",
    labelnames=["flow"],
    registry=final_registry,
)


def push_metrics(registry: CollectorRegistry) -> None:
    push_to_gateway(settings.push_gateway, job=settings.service, registry=registry)


def record_ending(name: str, status: str) -> None:
    FLOW_STATUS.labels(name, status).inc()
    FLOWS_FINISHED.labels(name).inc()
    push_metrics(final_registry)


def on_finish(flow: Flow, flow_run: FlowRun, state: State):
    record_ending(flow.name, state.type.value)


TASK_DEFAULT_KWARGS = {
    "retries": 2,
    "retry_delay_seconds": 10,
    "log_prints": False,
    "timeout_seconds": 3600,  # An hour timeout per task
    "cache_result_in_memory": False,
}


FLOW_DEFAULT_KWARGS = {
    "timeout_seconds": 3600 * 24 * 7,  # A week timeout per flow
    "on_crashed": [on_finish],
    "on_failure": [on_finish],
    "on_completion": [on_finish],
    "on_cancellation": [on_finish],
    "log_prints": False,
    "cache_result_in_memory": False,
}


def data_task(**kwargs):
    def decorate(func: Callable) -> Callable:
        tracer = get_tracer(settings.service)
        final_kwargs = {**TASK_DEFAULT_KWARGS, **kwargs}
        name = kwargs.get("name", func.__name__)

        @task(**final_kwargs)
        @wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(name, kind=SpanKind.SERVER) as span:
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
                    push_metrics(initial_registry)
                    start = time.perf_counter()
                    result = func(*args, **kwargs)
                    elapsed = time.perf_counter() - start
                    FLOW_PROCESSING_TIME.labels(name).observe(elapsed)

                    # Note because flows can crash, we don't handle the post-execution
                    # prometheus here
                    if isinstance(result, State):
                        if result.type != StateType.COMPLETED:
                            span.set_status(StatusCode.OK)
                        else:
                            span.set_status(StatusCode.ERROR, description=result.message)
                    else:
                        span.set_status(StatusCode.OK)
                    push_metrics(interim_registry)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(StatusCode.ERROR, description=f"{type(e).__name__}: {e}")
                    raise

        return wrapper

    return decorate
