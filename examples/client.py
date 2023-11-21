import logging
import os
import signal
import sys
import time
import traceback
from typing import Any, Dict

import cv2

from era_5g_client.client import NetAppClient, RunTaskMode
from era_5g_client.dataclasses import MiddlewareInfo
from era_5g_client.exceptions import FailedToConnect
from era_5g_interface.channels import CallbackInfoClient, ChannelType

stopped = False

# Video from source flag
FROM_SOURCE = os.getenv("FROM_SOURCE", "").lower() in ("true", "1")
# ip address or hostname of the middleware server
MIDDLEWARE_ADDRESS = os.getenv("MIDDLEWARE_ADDRESS", "127.0.0.1")
# middleware user
MIDDLEWARE_USER = os.getenv("MIDDLEWARE_USER", "00000000-0000-0000-0000-000000000000")
# middleware password
MIDDLEWARE_PASSWORD = os.getenv("MIDDLEWARE_PASSWORD", "password")
# middleware 5G-ERA Network Application id (task id)
MIDDLEWARE_TASK_ID = os.getenv("MIDDLEWARE_TASK_ID", "00000000-0000-0000-0000-000000000000")
# middleware robot id (robot id)
MIDDLEWARE_ROBOT_ID = os.getenv("MIDDLEWARE_ROBOT_ID", "00000000-0000-0000-0000-000000000000")

if not FROM_SOURCE:
    # test video file
    try:
        TEST_VIDEO_FILE = os.environ["TEST_VIDEO_FILE"]
    except KeyError as e:
        raise Exception(f"Failed to run example, env variable {e} not set.")

    if not os.path.isfile(TEST_VIDEO_FILE):
        raise Exception("TEST_VIDEO_FILE does not contain valid path to a file.")

# Enable logging.
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format="%(asctime)s [%(levelname)8s] %(name)s: %(message)s")


def get_results(results: Dict[str, Any]) -> None:
    """Callback which process the results from the 5G-ERA Network Application.

    Args:
        results (str): The results in json format.
    """

    print(results)
    pass


def main() -> None:
    """Creates the client class and starts the data transfer."""

    client = None
    global stopped
    stopped = False

    def signal_handler(sig: int, *_) -> None:
        logging.info(f"Terminating ({signal.Signals(sig).name})...")
        global stopped
        stopped = True

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # creates an instance of 5G-ERA Network Application client with results callback
        client = NetAppClient(callbacks_info={"results": CallbackInfoClient(ChannelType.JSON, get_results)})
        # authenticates with the middleware
        client.connect_to_middleware(MiddlewareInfo(MIDDLEWARE_ADDRESS, MIDDLEWARE_USER, MIDDLEWARE_PASSWORD))
        # run task, wait until is ready and register with it
        client.run_task(MIDDLEWARE_TASK_ID, MIDDLEWARE_ROBOT_ID, True, RunTaskMode.WAIT_AND_REGISTER)

        if FROM_SOURCE:
            # creates a video capture to pass images to the 5G-ERA Network Application either from webcam ...
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                raise Exception("Cannot open camera")
        else:
            # or from video file
            cap = cv2.VideoCapture(TEST_VIDEO_FILE)
            if not cap.isOpened():
                raise Exception("Cannot open video file")

        while not stopped:
            ret, frame = cap.read()
            timestamp = time.perf_counter_ns()
            if not ret:
                break
            resized = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_AREA)
            client.send_image(resized, "image", ChannelType.JPEG, timestamp)

    except FailedToConnect as ex:
        print(f"Failed to connect to server ({ex})")
    except KeyboardInterrupt:
        print("Terminating...")
    except Exception as ex:
        traceback.print_exc()
        print(f"Failed to create client instance ({repr(ex)})")
    finally:
        if client is not None:
            client.disconnect()


if __name__ == "__main__":
    main()
