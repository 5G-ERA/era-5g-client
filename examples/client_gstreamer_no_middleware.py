import logging
import os
import signal
import traceback
from threading import Thread
from types import FrameType
from typing import Any, Dict, Optional

from era_5g_client.client_base import NetAppClientBase
from era_5g_client.data_sender_gstreamer_from_file import DataSenderGStreamerFromFile
from era_5g_client.data_sender_gstreamer_from_source import DataSenderGStreamerFromSource
from era_5g_client.dataclasses import NetAppLocation
from era_5g_client.exceptions import FailedToConnect

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

    client: Optional[NetAppClientBase] = None
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
        client = NetAppClientBase(get_results)
        # register with an ad-hoc deployed NetApp
        client.register(NetAppLocation(NETAPP_ADDRESS, NETAPP_PORT), gstreamer=True)

        if not client.gstreamer_port:
            logging.error("Missing port for GStreamer")
            client.disconnect()
            return

        if FROM_SOURCE:
            # creates a data sender which will pass images to the NetApp either from webcam ...
            data_src = (
                "v4l2src device=/dev/video0 ! video/x-raw, format=YUY2, width=640, height=480, "
                + "pixel-aspect-ratio=1/1 ! videoconvert ! appsink"
            )
            sender = DataSenderGStreamerFromSource(NETAPP_ADDRESS, client.gstreamer_port, data_src, 15, 640, 480, False)
            sender.start()
        else:
            # or from file
            sender = DataSenderGStreamerFromFile(NETAPP_ADDRESS, client.gstreamer_port, TEST_VIDEO_FILE, 15, 640, 480)
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
