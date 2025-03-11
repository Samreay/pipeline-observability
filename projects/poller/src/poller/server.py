import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
import os
from prometheus_fastapi_instrumentator import Instrumentator
from loguru import logger
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
import httpx

HTTPXClientInstrumentor().instrument()  # This ensures httpx requests are traced


endpoint = os.getenv("RECEIVER_ENDPOINT", "http://localhost:8000")
logger.info(f"Polling {endpoint} for new random numbers.")


async def poll() -> None:
    logger.info("Polling for a new random number.")
    async with httpx.AsyncClient(timeout=1) as client:
        try:
            response = await client.get(endpoint, timeout=1)
            response.raise_for_status()
            logger.info(f"Received random number: {response.json()['value']}")
        except Exception as e:
            logger.error(f"Failed to fetch random number: {e!r}")


async def poller():
    logger.info("Poller is running!")
    while True:
        await poll()
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    future = asyncio.gather(poller())
    logger.info("Application started.")
    yield
    future.cancel()


app = FastAPI(lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


@app.get("/")
async def read_root():
    return {"message": "Poller is running!"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002, log_config=None, log_level=None)
