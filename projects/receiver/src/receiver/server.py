from fastapi import FastAPI
from random import randint
from prometheus_fastapi_instrumentator import Instrumentator
from loguru import logger

app = FastAPI()
Instrumentator().instrument(app).expose(app)


@app.get("/")
def read_root():
    logger.info("Received request for a new random number. How exciting!")
    return {"value": randint(0, 100)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0")
