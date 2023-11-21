import logging
import os
import signal
import sys
import time
import traceback
from typing import Any, Dict

import cv2

from era_5g_client.client_base import NetAppClientBase
from era_5g_client.exceptions import FailedToConnect
from era_5g_interface.channels import CallbackInfoClient, ChannelType

stopped = False

# Video from source flag
FROM_SOURCE = os.getenv("FROM_SOURCE", "").lower() in ("true", "1")
# URL of the network application, including the schema and port (e.g., http://localhost:5896)
NETAPP_ADDRESS = os.getenv("NETAPP_ADDRESS", "http//localhost:5896")

# test video file
if not FROM_SOURCE:
    try:
        TEST_VIDEO_FILE = os.environ["TEST_VIDEO_FILE"]
    except KeyError as e:
        raise Exception(f"Failed to run example, env variable {e} not set.")

    if not os.path.isfile(TEST_VIDEO_FILE):
        raise Exception("TEST_VIDEO_FILE does not contain valid path to a file.")

# Enable logging.
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def get_results(results: Dict[str, Any]) -> None:
    """Callback which process the results from the 5G-ERA Network Application.

    Args:
        results (str): The results in json format
    """

    print(results)


def main() -> None:
    """Creates the client class and starts the data transfer."""

    client = None
    global stopped
    stopped = False

    def signal_handler(sig: int, *_) -> None:
        global stopped
        stopped = True
        print(f"Terminating ({signal.Signals(sig).name})...")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # creates an instance of 5G-ERA Network Application client with results callback
        client = NetAppClientBase({"results": CallbackInfoClient(ChannelType.JSON, get_results)})
        # register with an ad-hoc deployed 5G-ERA Network Application
        client.register(NETAPP_ADDRESS)

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
            timestamp = time.time_ns()
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
