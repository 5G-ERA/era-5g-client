import logging
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Union

import cv2
import numpy as np
import socketio
import ujson
from socketio.exceptions import ConnectionError

from era_5g_client.exceptions import BackPressureException, FailedToConnect
from era_5g_interface.dataclasses.control_command import ControlCmdType, ControlCommand
from era_5g_interface.h264_encoder import H264Encoder, H264EncoderError


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
        logging_level: int = logging.INFO,
        socketio_debug: bool = False,
        stats: bool = False,
        back_pressure_size: Optional[int] = 5,
    ) -> None:
        """Constructor.

        Args:

            results_event (Callable): Callback where results will arrive.
            image_error_event (Callable, optional): Callback which is emitted when server
                failed to process the incoming image.
            json_error_event (Callable, optional): Callback which is emitted when server
                failed to process the incoming json data.
            control_cmd_event (Callable, optional): Callback for receiving data that are
                sent as a result of performing a control command (e.g. NetApp state
                obtained by get-state command).
            control_cmd_error_event (Callable, optional): Callback which is emitted when
                server failed to process the incoming control command.

        Raises:
            FailedToConnect: When connection to the middleware could not be set or
                login failed
            FailedToObtainPlan: When the plan was not successfully returned from
                the middleware
        """
        self._sio = socketio.Client(logger=socketio_debug, reconnection_attempts=1, handle_sigint=False, json=ujson)
        self.netapp_address: Union[str, None] = None
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
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging_level)
        self.stats = stats

        if back_pressure_size is not None and back_pressure_size < 1:
            raise ValueError("Invalid value for back_pressure_size.")

        self.back_pressure_size = back_pressure_size
        if self.stats:
            self.sizes: List[int] = []

    def register(
        self,
        netapp_address: str,
        args: Optional[Dict[str, Any]] = None,
        wait_until_available: bool = False,
        wait_timeout: int = -1,
    ) -> None:
        """Calls the /register endpoint of the NetApp interface and if the
        registration is successful, it sets up the WebSocket connection for
        results retrieval.

        Args:
            netapp_address (str): The URL of the network application interface,
                including the scheme and optionally port and path to the interface,
                e.g. http://localhost:80 or http://gateway/path_to_interface
            args (Optional[Dict], optional): Optional parameters to be passed to
            the NetApp, in the form of dict. Defaults to None.
            wait_until_available: If True, the client will repeatedly try to register
                with the Network Application until it is available. Defaults to False.
            wait_timeout: How long the client will try to connect to network application.
                Only used if wait_until_available is True. If negative, the client
                will wait indefinitely. Defaults to -1.

        Raises:
            FailedToConnect: _description_

        Returns:
            Response: response from the NetApp.
        """

        self.netapp_address = netapp_address
        namespaces_to_connect = ["/data", "/control", "/results"]
        start_time = time.time()
        while True:
            try:
                self.logger.debug("Trying to connect to the network application")
                self._sio.connect(
                    netapp_address,
                    namespaces=namespaces_to_connect,
                    wait_timeout=10,
                )
                break
            except ConnectionError as ex:
                self.logger.debug(f"Failed to connect: {ex}")
                if not wait_until_available or (wait_timeout > 0 and start_time + wait_timeout < time.time()):
                    raise FailedToConnect(ex)
                self.logger.warning("Failed to connect to network application. Retrying in 1 second.")
                time.sleep(1)

        self.logger.info(f"Client connected to namespaces: {namespaces_to_connect}")

        if args and args.get("h264") is True:
            self.h264_encoder = H264Encoder(float(args["fps"]), int(args["width"]), int(args["height"]))

        if args is None:  # TODO would be probably better to handle in ControlCommand
            args = {}

        # initialize the network application with desired parameters using the init command
        control_cmd = ControlCommand(ControlCmdType.INIT, clear_queue=False, data=args)
        self.send_control_command(control_cmd)

    def disconnect(self) -> None:
        """Disconnects the WebSocket connection."""
        self._sio.disconnect()
        if self.stats:
            self.logger.info(
                f"Transferred bytes sum: {sum(self.sizes)} "
                f"median: {statistics.median(self.sizes)} "
                f"mean: {statistics.mean(self.sizes)} "
                f"min: {min(self.sizes)} "
                f"max: {max(self.sizes)} "
            )

    def wait(self) -> None:
        """Blocking infinite waiting."""
        self._sio.wait()

    def on_connect_event(self) -> None:
        """The callback called once the connection to the NetApp is made."""
        self.logger.info("Connected to server")

    def on_connect_error(self, message: Optional[str] = None) -> None:
        """The callback called on connection error."""
        self.logger.error(f"Connection error: {message}")
        self.disconnect()

    def send_image_ws(
        self,
        frame: np.ndarray,
        timestamp: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        can_be_dropped=True,
    ):
        """Encodes the image frame to the jpg or h264 format and sends it over
        the websocket, to the /data namespace.

        Args:
            frame (np.ndarray): Image frame
            timestamp (Optional[int], optional): Frame timestamp
            metadata (Optional[str], optional): Optional metadata
            can_be_dropped: if data can be lost due to back pressure
        """

        try:
            if self.h264_encoder:
                frame_encoded = self.h264_encoder.encode_ndarray(frame)
            else:
                _, frame_jpeg = cv2.imencode(".jpg", frame)
                frame_encoded = frame_jpeg.tobytes()
            if self.stats:
                self.sizes.append(len(frame_encoded))
                self.logger.debug(f"Frame data size: {self.sizes[-1]}")
            data = {"timestamp": timestamp, "frame": frame_encoded}
            if metadata:
                data["metadata"] = metadata
            # TODO for h264 the back pressure is disabled now - make it able to drop non-key frames
            self.send_image_ws_raw(data, can_be_dropped and self.h264_encoder is None)
        except H264EncoderError as e:
            self.logger.error(f"H264 encoder error: {e}")
            self.disconnect()
            raise e

    def _apply_back_pressure(self) -> None:
        if self.back_pressure_size is not None and self._sio.eio.queue.qsize() > self.back_pressure_size:
            raise BackPressureException()

    def send_image_ws_raw(self, data: Dict[str, Any], can_be_dropped=True) -> None:
        """Sends already encoded image data to /data namespace.

        Args:
            data (Dict): _description_
            can_be_dropped: if data can be lost due to back pressure
        """
        if can_be_dropped:
            self._apply_back_pressure()
        self._sio.emit("image", data, "/data")

    def send_json_ws(self, json: Dict[str, Any], can_be_dropped=True) -> None:
        """Sends netapp-specific json data using the websockets.

        Args:
            json (dict): Json data in the form of Python dictionary
            can_be_dropped: if data can be lost due to back pressure
        """
        if can_be_dropped:
            self._apply_back_pressure()
        self._sio.emit("json", json, "/data")

    def send_control_command(self, control_command: ControlCommand) -> None:
        """Sends control command over the websocket.

        Args:
            control_command (ControlCommand): Control command to be sent.
        """

        self._sio.call("command", asdict(control_command), "/control")
