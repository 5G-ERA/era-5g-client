import os
import signal
import traceback
from threading import Thread
from types import FrameType
from typing import Optional

from era_5g_client.client_gstreamer import NetAppClientGstreamer
from era_5g_client.data_sender_gstreamer_from_file import DataSenderGStreamerFromFile
from era_5g_client.data_sender_gstreamer_from_source import DataSenderGStreamerFromSource
from era_5g_client.exceptions import FailedToConnect

# Video from source flag
FROM_SOURCE = os.getenv("FROM_SOURCE", False)
# ip address or hostname of the middleware server
MIDDLEWARE_ADDRESS = os.getenv("MIDDLEWARE_ADDRESS", "127.0.0.1")
# middleware user
MIDDLEWARE_USER = os.getenv("MIDDLEWARE_USER", "00000000-0000-0000-0000-000000000000")
# middleware password
MIDDLEWARE_PASSWORD = os.getenv("MIDDLEWARE_PASSWORD", "password")
# middleware NetApp id (task id)
MIDDLEWARE_TASK_ID = os.getenv("MIDDLEWARE_TASK_ID", "00000000-0000-0000-0000-000000000000")
# test video file
TEST_VIDEO_FILE = os.getenv("TEST_VIDEO_FILE", "../../../../assets/2017_01_02_001021_s.mp4")


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

    client: Optional[NetAppClientGstreamer] = None
    sender: Optional[Thread] = None

    def signal_handler(sig: int, frame: Optional[FrameType]) -> None:
        print(f"Terminating ({signal.Signals(sig).name})...")
        if sender is not None:
            sender.stop()  # type: ignore  # TODO ZM: lazy to fix that atm (classes should have common base)
        if client is not None:
            client.disconnect()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # creates the NetApp client with gstreamer extension
        client = NetAppClientGstreamer(
            MIDDLEWARE_ADDRESS, MIDDLEWARE_USER, MIDDLEWARE_PASSWORD, MIDDLEWARE_TASK_ID, True, get_results, True, True
        )

        assert client.netapp_host
        assert client.gstreamer_port

        # register the client with the NetApp
        client.register()
        if FROM_SOURCE:
            # creates a data sender which will pass images to the NetApp either from webcam ...
            data_src = (
                "v4l2src device=/dev/video0 ! video/x-raw, format=YUY2, width=640, height=480, "
                + "pixel-aspect-ratio=1/1 ! videoconvert ! appsink"
            )
            sender = DataSenderGStreamerFromSource(
                client.netapp_host, client.gstreamer_port, data_src, 15, 640, 480, False
            )
            sender.start()
        else:
            # or from file
            sender = DataSenderGStreamerFromFile(
                client.netapp_host, client.gstreamer_port, TEST_VIDEO_FILE, 15, 640, 480
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