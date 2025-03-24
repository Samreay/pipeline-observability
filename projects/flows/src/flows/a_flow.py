from random import random
import time
from common.prefect_utils import data_flow, data_task

from common.log import configure_logging, get_logger
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    flow: str = Field(default="some-flow")


@data_task()
def some_subtask():
    logger = get_logger()
    logger.info("Hello, subtask!")
    time.sleep(0.5 * random())

    return 42


@data_task()
def some_task():
    logger = get_logger()
    logger.info("Hello, world!")
    time.sleep(2 * random())
    some_subtask()
    if random() < 0.2:
        raise ValueError("Random error!")


@data_flow()
def some_flow():
    configure_logging("flows")
    if random() < 0.2:
        some_task()
    some_subtask()


@data_flow()
def poll_something():
    configure_logging("flows")
    some_subtask()


if __name__ == "__main__":
    flow_to_serve = Settings().flow
    if flow_to_serve == "some-flow":
        some_flow.serve(name="some-flow", interval=2)
    elif flow_to_serve == "poll-something":
        poll_something.serve(name="poll-something", interval=1)
