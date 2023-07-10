import base64
import logging
import os
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Dict, Optional, Union

import cv2
import numpy as np
import socketio
from socketio.exceptions import ConnectionError

from era_5g_client.dataclasses import NetAppLocation
from era_5g_client.exceptions import FailedToConnect
from era_5g_interface.dataclasses.control_command import ControlCmdType, ControlCommand
from era_5g_interface.h264_encoder import H264Encoder, H264EncoderError  # type: ignore

# TODO: type ignored will be removed after release on pip

logger = logging.getLogger(__name__)

# port of the netapp's server
NETAPP_PORT = int(os.getenv("NETAPP_PORT", 5896))


class NetAppClientBase:
    """Basic implementation of the NetApp client.

    It creates the Requests object with session and bind callbacks for
    connection info and results from the NetApp.
    """

    def __init__(
        self,
        results_event: Callable,
        image_error_event: Optional[Callable] = None,
        json_error_event: Optional[Callable] = None,
        control_cmd_event: Optional[Callable] = None,
        control_cmd_error_event: Optional[Callable] = None,
    ) -> None:
        """Constructor.

        Args:

            results_event (Callable): Callback where results will arrive.
            image_error_event (Callable, optional): Callback which is emited when server
                failed to process the incoming image.
            json_error_event (Callable, optional): Callback which is emited when server
                failed to process the incoming json data.
            control_cmd_event (Callable, optional): Callback for receiving data that are
                sent as a result of performing a control command (e.g. NetApp state
                obtained by get-state command).
            control_cmd_error_event (Callable, optional): Callback which is emited when
                server failed to process the incoming control command.

        Raises:
            FailedToConnect: When connection to the middleware could not be set or
                login failed
            FailedToObtainPlan: When the plan was not successfully returned from
                the middleware
        """

        self._sio = socketio.Client()
        self.netapp_location: Union[NetAppLocation, None] = None
        self._sio.on("message", results_event, namespace="/results")
        self._sio.on("connect", self.on_connect_event, namespace="/results")
        self._sio.on("image_error", image_error_event, namespace="/data")
        self._sio.on("json_error", json_error_event, namespace="/data")
        self._sio.on("connect_error", self.on_connect_error, namespace="/results")
        self._sio.on("control_cmd_result", control_cmd_event, namespace="/control")
        self._sio.on("control_cmd_error", control_cmd_error_event, namespace="/control")
        self._session_cookie: Optional[str] = None
        self.h264_encoder: Optional[H264Encoder] = None
        self._image_error_event = image_error_event
        self._json_error_event = json_error_event
        self._control_cmd_event = control_cmd_event
        self._control_cmd_error_event = control_cmd_error_event

    def register(
        self,
        netapp_location: NetAppLocation,
        args: Optional[Dict] = None,
        wait_until_available: bool = False,
        wait_timeout: int = -1,
    ) -> None:
        """Calls the /register endpoint of the NetApp interface and if the
        registration is successful, it sets up the WebSocket connection for
        results retrieval.

        Args:
            netapp_location (NetAppLocation): The URI and port of the NetApp interface.
            args (Optional[Dict], optional): Optional parameters to be passed to
            the NetApp, in the form of dict. Defaults to None.
            wait_until_available: If True, the client will repeatedly try to register
                with the Network Application until it is available. Defaults to False.
            wait_timeout: How long the client will try to connect to network application.
                Only used if wait_until_available is True. If negative, the client
                will waits indefinitely. Defaults to -1.

        Raises:
            FailedToConnect: _description_

        Returns:
            Response: response from the NetApp.
        """

        self.netapp_location = netapp_location

        namespaces_to_connect = ["/data", "/control", "/results"]
        start_time = time.time()
        while True:
            try:
                self._sio.connect(
                    self.netapp_location.build_api_endpoint(""),
                    namespaces=namespaces_to_connect,
                    wait_timeout=10,
                )
                break
            except ConnectionError as ex:
                if not wait_until_available or (wait_timeout > 0 and start_time + wait_timeout < time.time()):
                    raise FailedToConnect(ex)
                logging.warn("Failed to connect to network application. Retrying in 1 second.")
                time.sleep(1)
        logger.info(f"Client connected to namespaces: {namespaces_to_connect}")

        if args and args.get("h264") is True:
            self.h264_encoder = H264Encoder(float(args["fps"]), int(args["width"]), int(args["height"]))

        if args is None:  # TODO would be probably better to handle in ControlCommand
            args = {}

        # initialize the network application with desired parameters using the set_state command
        control_cmd = ControlCommand(ControlCmdType.SET_STATE, clear_queue=True, data=args)
        self.send_control_command(control_cmd)

    def disconnect(self) -> None:
        """Disconnects the WebSocket connection."""
        self._sio.disconnect()

    def wait(self) -> None:
        """Blocking infinite waiting."""
        self._sio.wait()

    def on_connect_event(self) -> None:
        """The callback called once the connection to the NetApp is made."""
        logger.info("Connected to server")

    def on_connect_error(self, message=None) -> None:
        """The callback called on connection error."""
        logger.error(f"Connection error: {message}")
        self.disconnect()

    def send_image_ws(self, frame: np.ndarray, timestamp: Optional[int] = None, metadata: Optional[str] = None):
        """Encodes the image frame to the jpg or h264 format and sends it over
        the websocket, to the /data namespace.

        Args:
            frame (np.ndarray): Image frame
            timestamp (Optional[int], optional): Frame timestamp
            metadata (Optional[str], optional): Optional metadata
        """

        try:
            if self.h264_encoder:
                frame_encoded = self.h264_encoder.encode_ndarray(frame)
            else:
                _, frame_jpeg = cv2.imencode(".jpg", frame)
                frame_encoded = base64.b64encode(frame_jpeg)
            data = {"timestamp": timestamp, "frame": frame_encoded}
            if metadata:
                data["metadata"] = metadata
            self._sio.emit("image", data, "/data")
        except H264EncoderError as e:
            logger.error(f"H264 encoder error: {e}")
            self.disconnect()
            raise e
        except Exception as e:
            logger.error(f"Send image emit error: {e}")
            self.disconnect()
            raise e

    def send_image_ws_raw(self, data: Dict):
        """Sends already encoded image data to /data namespace.

        Args:
            data (Dict): _description_
        """
        self._sio.emit("image", data, "/data")

    def send_json_ws(self, json: Dict) -> None:
        """Sends netapp-specific json data using the websockets.

        Args:
            json (dict): Json data in the form of Python dictionary
        """
        self._sio.emit("json", json, "/data")

    def send_control_command(self, control_command):
        """Sends control command over the websocket.

        Args:
            control_command (ControlCommand): Control command to be sent.
        """

        self._sio.call("command", asdict(control_command), "/control")
