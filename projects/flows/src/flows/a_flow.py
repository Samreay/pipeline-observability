from random import random
import time
from common.prefect_utils import trace_func
from prefect import flow, task

from common.log import configure_logging, get_logger


@task
@trace_func("flows")
def some_subtask():
    logger = get_logger()
    logger.info("Hello, subtask!")
    time.sleep(0.1)
    if random() < 0.2:
        raise ValueError("Random error!")
    return 42


@task
@trace_func("flows")
def some_task():
    logger = get_logger()
    logger.info("Hello, world!")
    time.sleep(1)
    return some_subtask()


@flow
@trace_func("flows")
def some_flow():
    configure_logging("flows")
    some_task()
    some_subtask()


if __name__ == "__main__":
    some_flow.serve(name="some-flow", interval=5)
