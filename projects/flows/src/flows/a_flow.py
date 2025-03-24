from random import random
import time
from common.prefect_utils import data_flow, data_task

from common.log import configure_logging, get_logger


@data_task()
def some_subtask():
    logger = get_logger()
    logger.info("Hello, subtask!")
    time.sleep(random())

    return 42


@data_task()
def some_task():
    logger = get_logger()
    logger.info("Hello, world!")
    time.sleep(1)
    some_subtask()
    if random() < 0.2:
        raise ValueError("Random error!")


@data_flow()
def some_flow():
    configure_logging("flows")
    some_task()
    some_subtask()


if __name__ == "__main__":
    some_flow.serve(name="some-flow", interval=2)
