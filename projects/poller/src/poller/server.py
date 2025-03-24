import asyncio
from contextlib import asynccontextmanager
from common.tracing import get_tracer
from fastapi import FastAPI
import os
from common.log import configure_logging
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
import httpx
from common.prom import PrometheusMiddleware, metrics
from random import random
from loguru import logger

service = "poller"
tracer = get_tracer(service)
configure_logging(service)
endpoint = os.getenv("RECEIVER_ENDPOINT", "http://localhost:8000")
logger.info(f"Polling {endpoint} for new random numbers.")


async def poll() -> None:
    with tracer.start_as_current_span("polling_for_random_number"):
        logger.info("Polling for a new random number.")
        async with httpx.AsyncClient(timeout=1) as client:
            try:
                tmp_endpoint = endpoint
                if random() < 0.2:
                    tmp_endpoint += "/slow"
                response = await client.get(tmp_endpoint, timeout=10)
                response.raise_for_status()
                logger.info(f"Received random number: {response.json()['value']}")
            except Exception as e:
                logger.error(f"Failed to fetch random number: {e!r}")


async def poller():
    logger.info("Poller is running!")
    while True:
        await poll()
        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    future = asyncio.gather(poller())
    logger.info("Application started.")
    yield
    future.cancel()


HTTPXClientInstrumentor().instrument()  # This ensures httpx requests are traced
app = FastAPI(lifespan=lifespan)
app.add_middleware(PrometheusMiddleware, service=service)
app.add_route("/metrics", metrics)


@app.get("/")
async def read_root():
    return {"message": "Poller is running!"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002, log_config=None, log_level=None)
