from prometheus_client import CollectorRegistry, Counter, push_to_gateway

registry = CollectorRegistry()
counter = Counter("some_counter", "A counter", registry=registry)
counter.inc()
push_to_gateway("http://pushgateway:80", job="flows", registry=registry)
