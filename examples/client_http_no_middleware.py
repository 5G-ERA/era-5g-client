from __future__ import annotations

import logging
import math
import os
import signal
import time
import traceback
from types import FrameType
from typing import Any, Dict, Optional

import cv2

from era_5g_client.client import NetAppClient
from era_5g_client.exceptions import FailedToConnect

stopped = False

DEBUG_PRINT_SCORE = False  # useful for FPS detector
DEBUG_PRINT_DELAY = False  # prints the delay between capturing image and receiving the results

# Video from source flag
FROM_SOURCE = os.getenv("FROM_SOURCE", "").lower() in ("true", "1")
# ip address or hostname of the computer, where the netapp is deployed
NETAPP_ADDRESS = os.getenv("NETAPP_ADDRESS", "127.0.0.1")
# port of the netapp's server
NETAPP_PORT = int(os.getenv("NETAPP_PORT", 5896))
# test video file
if not FROM_SOURCE:
    try:
        TEST_VIDEO_FILE = os.environ["TEST_VIDEO_FILE"]
    except KeyError as e:
        raise Exception(f"Failed to run example, env variable {e} not set.")

    if not os.path.isfile(TEST_VIDEO_FILE):
        raise Exception("TEST_VIDEO_FILE does not contain valid path to a file.")


def get_results(results: Dict[str, Any]) -> None:
    """Callback which process the results from the NetApp.

    Args:
        results (str): The results in json format
    """

    print(results)


def main() -> None:
    """Creates the client class and starts the data transfer."""

    logging.getLogger().setLevel(logging.INFO)

    client = None
    global stopped
    stopped = False

    def signal_handler(sig: int, frame: Optional[FrameType]) -> None:
        global stopped
        stopped = True
        print(f"Terminating ({signal.Signals(sig).name})...")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # creates the NetApp client with gstreamer extension
        client = NetAppClient("", "", "", "", True, get_results, False, False, NETAPP_ADDRESS, NETAPP_PORT)
        # register the client with the NetApp
        client.register()
        if FROM_SOURCE:
            # creates a video capture to pass images to the NetApp either from webcam ...
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
            timestamp = math.floor(time.time() * 100)
            if not ret:
                break
            resized = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_AREA)
            timestamp_str = str(timestamp)
            client.send_image_http(resized, timestamp_str)

    except FailedToConnect as ex:
        print(f"Failed to connect to server ({ex})")
    except KeyboardInterrupt:
        print("Terminating...")
    except Exception as ex:
        traceback.print_exc()
        print(f"Failed to create client instance ({ex})")
    finally:
        if client is not None:
            client.disconnect()


if __name__ == "__main__":
    main()
