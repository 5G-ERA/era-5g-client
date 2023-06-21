import base64
import logging
import os
from collections.abc import Callable
from dataclasses import asdict
from typing import Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
import socketio
from socketio.exceptions import ConnectionError  # type: ignore

from era_5g_client.dataclasses import NetAppLocation
from era_5g_client.exceptions import FailedToConnect
from era_5g_interface.dataclasses.control_command import ControlCmdType, ControlCommand  # type: ignore

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
        # holds the gstreamer port
        self.gstreamer_port: Optional[int] = None
        self._buffer: List[Tuple[np.ndarray, Optional[str]]] = []
        self._image_error_event = image_error_event
        self._json_error_event = json_error_event
        self._control_cmd_event = control_cmd_event
        self._control_cmd_error_event = control_cmd_error_event

    def register(
        self,
        netapp_location: NetAppLocation,
        args: Optional[Dict] = None,
    ) -> None:
        """Calls the /register endpoint of the NetApp interface and if the
        registration is successful, it sets up the WebSocket connection for
        results retrieval.

        Args:
            netapp_location (NetAppLocation): The URI and port of the NetApp interface.
            gstreamer (Optional[bool], optional): Indicates if a GStreamer pipeline
                should be initialized for image transport. Defaults to False.
            args (Optional[Dict], optional): Optional parameters to be passed to
            the NetApp, in the form of dict. Defaults to None.

        Raises:
            FailedToConnect: _description_

        Returns:
            Response: response from the NetApp.
        """

        self.netapp_location = netapp_location

        namespaces_to_connect = ["/data", "/control", "/results"]
        try:
            self._sio.connect(
                self.netapp_location.build_api_endpoint(""),
                namespaces=namespaces_to_connect,
                wait_timeout=10,
            )
        except ConnectionError as ex:
            raise FailedToConnect(ex)
        logging.info(f"Client connected to namespaces: {namespaces_to_connect}")
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
        print("Connected to server")

    def on_connect_error(self, data: str) -> None:
        """The callback called on connection error."""
        print(f"Connection error: {data}")
        # self.disconnect()

    def send_image_ws(self, frame: np.ndarray, timestamp: Optional[str] = None):
        """Encodes the image frame to the jpg format and sends it over the
        websocket, to the /data namespace.

        Args:
            frame (np.ndarray): Image frame
            timestamp (Optional[str], optional): Frame timestamp The timestamp format
            is defined by the NetApp. Defaults to None.
        """
        _, img_encoded = cv2.imencode(".jpg", frame)
        f = base64.b64encode(img_encoded)
        self._sio.emit("image", {"timestamp": timestamp, "frame": f}, "/data")

    def send_json_ws(self, json: dict) -> None:
        """Sends netapp-specific json data using the websockets.

        Args:
            json (dict): Json data in the form of Python dictionary
        """
        self._sio.call("json", json, "/data")

    def send_control_command(self, control_command):
        """Sends control command over the websocket.

        Args:
            control_command (ControlCommand): Control command to be sent.
        """

        self._sio.emit("command", asdict(control_command), "/control")
