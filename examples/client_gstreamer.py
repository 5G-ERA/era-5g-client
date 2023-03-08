import logging
import os
import signal
import traceback
from threading import Thread
from types import FrameType
from typing import Optional

from era_5g_client.client import NetAppClient, RunTaskMode
from era_5g_client.data_sender_gstreamer_from_file import DataSenderGStreamerFromFile
from era_5g_client.data_sender_gstreamer_from_source import DataSenderGStreamerFromSource
from era_5g_client.dataclasses import MiddlewareInfo
from era_5g_client.exceptions import FailedToConnect

# Video from source flag
FROM_SOURCE = os.getenv("FROM_SOURCE", "").lower() in ("true", "1")
# ip address or hostname of the middleware server
MIDDLEWARE_ADDRESS = os.getenv("MIDDLEWARE_ADDRESS", "127.0.0.1")
# middleware user
MIDDLEWARE_USER = os.getenv("MIDDLEWARE_USER", "00000000-0000-0000-0000-000000000000")
# middleware password
MIDDLEWARE_PASSWORD = os.getenv("MIDDLEWARE_PASSWORD", "password")
# middleware NetApp id (task id)
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


def get_results(results: str) -> None:
    """
    Callback which process the results from the NetApp
    Args:
        results (str): The results in json format
    """

    print(results)
    pass


def main() -> None:
    """Creates the client class and starts the data transfer."""

    client: Optional[NetAppClient] = None
    sender: Optional[Thread] = None

    logging.getLogger().setLevel(logging.INFO)

    def signal_handler(sig: int, frame: Optional[FrameType]) -> None:
        logging.info(f"Terminating ({signal.Signals(sig).name})...")
        if sender is not None:
            sender.stop()  # type: ignore  # TODO ZM: lazy to fix that atm (classes should have common base)
        if client is not None:
            client.disconnect()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # creates an instance of NetApp client with results callback
        client = NetAppClient(get_results)
        # authenticates with the middleware
        client.connect_to_middleware(MiddlewareInfo(MIDDLEWARE_ADDRESS, MIDDLEWARE_USER, MIDDLEWARE_PASSWORD))
        # run task, wait untill is ready and register with it
        client.run_task(MIDDLEWARE_TASK_ID, MIDDLEWARE_ROBOT_ID, True, RunTaskMode.WAIT_AND_REGISTER, gstreamer=True)

        if not client.netapp_location:
            logging.error("The middleware did not provide NetApp's address")
            client.disconnect()
            return

        if not client.gstreamer_port:
            logging.error("The middleware did not provide port for GStreamer")
            client.disconnect()
            return

        if FROM_SOURCE:
            # creates a data sender which will pass images to the NetApp either from webcam ...
            data_src = (
                "v4l2src device=/dev/video0 ! video/x-raw, format=YUY2, width=640, height=480, "
                + "pixel-aspect-ratio=1/1 ! videoconvert ! appsink"
            )
            sender = DataSenderGStreamerFromSource(
                client.netapp_location.uri, client.gstreamer_port, data_src, 15, 640, 480, False
            )
            sender.start()
        else:

            # or from file
            sender = DataSenderGStreamerFromFile(
                client.netapp_location.uri, client.gstreamer_port, TEST_VIDEO_FILE, 15, 640, 480
            )
            sender.start()

        # waits infinitely
        client.wait()
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
