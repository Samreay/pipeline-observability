import os
from functools import lru_cache

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Tracer


class MinimalSpanProcessor(BatchSpanProcessor):
    def on_end(self, span: ReadableSpan) -> None:
        if span.kind == SpanKind.INTERNAL and span.attributes is not None:
            span_type = span.attributes.get("type", None)
            if span_type in (
                "http.request",
                "http.response.start",
                "http.response.body",
            ):
                return
        super().on_end(span=span)


@lru_cache
def get_tracer(service: str) -> Tracer:
    resource = Resource.create(attributes={"service.name": service})
    tracer = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer)
    if "OTEL_EXPORTER_OTLP_ENDPOINT" in os.environ:
        exporter = OTLPSpanExporter(endpoint=os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"])
        tracer.add_span_processor(MinimalSpanProcessor(exporter))
    return trace.get_tracer(service)
