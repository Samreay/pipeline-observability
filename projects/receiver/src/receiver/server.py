from common.prom import PrometheusMiddleware, metrics
from fastapi import FastAPI
from random import randint
from loguru import logger

service = "receiver"
app = FastAPI()
app.add_middleware(PrometheusMiddleware, service=service)
app.add_route("/metrics", metrics)


@app.get("/")
def read_root():
    logger.info("Received request for a new random number. How exciting!")
    return {"value": randint(0, 100)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0")
