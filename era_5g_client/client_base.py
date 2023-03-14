import base64
import os
from collections.abc import Callable
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import requests
import socketio
from requests import Response

from era_5g_client.dataclasses import NetAppLocation
from era_5g_client.exceptions import FailedToConnect, FailedToSendData, NetAppNotReady

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
    ) -> None:
        """Constructor.

        Args:

            results_event (Callable): callback where results will arrive
            image_error_event (Callable, optional): Callback which is emited when server
                failed to process the incoming image.
            json_error_event (Callable, optional): Callback which is emited when server
                failed to process the incoming json data.

        Raises:
            FailedToConnect: When connection to the middleware could not be set or
                login failed
            FailedToObtainPlan: When the plan was not successfully returned from
                the middleware
        """

        self._sio = socketio.Client()
        self._session = requests.session()
        self.netapp_location: Optional[NetAppLocation] = None
        self._sio.on("message", results_event, namespace="/results")
        self._sio.on("connect", self.on_connect_event, namespace="/results")
        self._sio.on("image_error", image_error_event, namespace="/data")
        self._sio.on("json_error", json_error_event, namespace="/data")
        self._sio.on("connect_error", self.on_connect_error, namespace="/results")
        self._session_cookie: Optional[str] = None
        self.ws_data: Optional[bool] = False
        # holds the gstreamer port
        self.gstreamer_port: Optional[int] = None
        self._buffer: List[Tuple[np.ndarray, Optional[str]]] = []

    def register(
        self,
        netapp_location: NetAppLocation,
        gstreamer: Optional[bool] = False,
        ws_data: Optional[bool] = False,
        args: Optional[Dict] = None,
    ) -> Response:
        """Calls the /register endpoint of the NetApp interface and if the
        registration is successful, it sets up the WebSocket connection for
        results retrieval.

        Args:
            netapp_location (NetAppLocation): The URI and port of the NetApp interface.
            gstreamer (Optional[bool], optional): Indicates if a GStreamer pipeline
                should be initialized for image transport. Defaults to False.
            ws_data (Optional[bool], optional): Indicates if a separate websocket channel
                for data transport should be set. Defaults to False.
            args (Optional[Dict], optional): Optional parameters to be passed to
            the NetApp, in the form of dict. Defaults to None.

        Raises:
            FailedToConnect: _description_

        Returns:
            Response: response from the NetApp.
        """

        self.netapp_location = netapp_location
        self.ws_data = ws_data

        merged_args = args
        if gstreamer:
            # pass gstreamer flag for the NetApp
            if args is None:
                merged_args = {"gstreamer": True}
            else:
                merged_args = {**args, **{"gstreamer": True}}

        response = self._session.post(
            self.netapp_location.build_api_endpoint("register"),
            json=merged_args,
            headers={"Content-Type": "application/json"},
        )

        if response.ok:
            # checks whether the NetApp responded with any data
            if response.content:
                try:
                    data = response.json()
                    if gstreamer:
                        if "port" in data:
                            self.gstreamer_port = data["port"]
                        else:
                            raise FailedToConnect(f"{response.status_code}: could not obtain the gstreamer port number")

                except ValueError as ex:
                    raise FailedToConnect(f"Decoding JSON has failed: {ex}, response: {response}")
        else:
            data = response.json()
            # checks if an error was returned
            if "error" in data:
                raise FailedToConnect(f"{response.status_code}: {data['error']}")
            else:
                raise FailedToConnect(f"{response.status_code}: Unknown error")

        self._session_cookie = response.cookies["session"]

        # creates the WebSocket connection
        if ws_data:
            self._sio.connect(
                self.netapp_location.build_api_endpoint(""),
                namespaces=["/results", "/data"],
                headers={"Cookie": f"session={self._session_cookie}"},
                wait_timeout=10,
            )
            print("connect")
        else:
            self._sio.connect(
                self.netapp_location.build_api_endpoint(""),
                namespaces=["/results"],
                headers={"Cookie": f"session={self._session_cookie}"},
                wait_timeout=10,
            )

        return response

    def disconnect(self) -> None:
        """Calls the /unregister endpoint of the server and disconnects the
        WebSocket connection."""

        if self.netapp_location:
            self._session.post(self.netapp_location.build_api_endpoint("unregister"))
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

    def send_image_http(self, frame: np.ndarray, timestamp: Optional[str] = None, batch_size: int = 1) -> None:
        """Encodes the image frame to the jpg format and sends it over the
        HTTP, to the /image endpoint.

        Args:
            frame (np.ndarray): image frame
            timestamp (str, optional): Frame timestamp The timestamp format
            is defined by the NetApp. Defaults to None.
            batch_size (int, optional): If higher than one, the images are
            send in batches. Defaults to 1
        """

        assert batch_size >= 1

        if not self.netapp_location:
            raise NetAppNotReady("The client does not know the netapp location")

        _, img_encoded = cv2.imencode(".jpg", frame)

        if len(self._buffer) < batch_size:
            self._buffer.append((img_encoded, timestamp))

        if len(self._buffer) == batch_size:
            # TODO find out right type annotation
            files = [("files", (f"image{i + 1}", self._buffer[i][0], "image/jpeg")) for i in range(batch_size)]

            timestamps: List[Optional[str]] = [b[1] for b in self._buffer]
            response = self._session.post(
                self.netapp_location.build_api_endpoint("image"),
                files=files,  # type: ignore
                params={"timestamps[]": timestamps},  # type: ignore
            )
            if not response.ok:
                raise FailedToSendData
            self._buffer.clear()

    def send_image_ws(self, frame: np.ndarray, timestamp: Optional[str] = None):
        """Encodes the image frame to the jpg format and sends it over the
        websocket, to the /data namespace.

        Args:
            frame (np.ndarray): Image frame
            timestamp (Optional[str], optional): Frame timestamp The timestamp format
            is defined by the NetApp. Defaults to None.
        """
        assert self.ws_data

        _, img_encoded = cv2.imencode(".jpg", frame)
        self._sio.emit("image", {"timestamp": timestamp, "frame": base64.b64encode(img_encoded)}, "/data")

    def send_json_ws(self, json: dict):
        """Sends netapp-specific json data.

        Args:
            json (dict): Json data in the form of Python dictionary
        """
        assert self.ws_data
        self._sio.emit("json", json, "/data")
