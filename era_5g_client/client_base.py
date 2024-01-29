import logging
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, Dict, Optional, Tuple, Union

import socketio
import ujson
from socketio.exceptions import ConnectionError

from era_5g_client.exceptions import FailedToConnect, FailedToInitialize
from era_5g_interface.channels import (
    COMMAND_ERROR_EVENT,
    COMMAND_EVENT,
    COMMAND_RESULT_EVENT,
    CONTROL_NAMESPACE,
    DATA_NAMESPACE,
    CallbackInfoClient,
)
from era_5g_interface.client_channels import ClientChannels
from era_5g_interface.dataclasses.control_command import ControlCmdType, ControlCommand


class NetAppClientBase:
    """Basic implementation of the 5G-ERA Network Application client.

    It creates websocket connection and bind callbacks from the 5G-ERA Network Application.
    How to send data? E.g.:
        client.send_image(frame, "image", ChannelType.H264, timestamp, encoding_options=h264_options)
        client.send_image(frame, "image", ChannelType.JPEG, timestamp, metadata)
        client.send_data({"message": "message text"}, "event_name")
        client.send_data({"message": "message text"}, "event_name", ChannelType.JSON_LZ4)
    How to create callbacks_info? E.g.:
        {
            "results": CallbackInfoClient(ChannelType.JSON, results_callback),
            "image": CallbackInfoClient(ChannelType.H264, image_callback, error_callback)
        }
    Callbacks have data parameter: e.g. def image_callback(data: Dict[str, Any]):
    Image data dict including decoded frame (data["frame"]) and send timestamp (data["timestamp"]).
    """

    def __init__(
        self,
        callbacks_info=Dict[str, CallbackInfoClient],
        command_result_callback: Optional[Callable] = None,
        command_error_callback: Optional[Callable] = None,
        logging_level: int = logging.INFO,
        socketio_debug: bool = False,
        stats: bool = False,
        back_pressure_size: Optional[int] = 5,
        recreate_coder_attempts_count: int = 5,
        reconnection_attempts: int = 3,
        disconnect_on_unhandled: bool = True,
    ) -> None:
        """Constructor.

        Args:
            callbacks_info (Dict[str, CallbackInfoClient]): Callbacks Info dictionary, key is custom event name.
                Example: {"results": CallbackInfoClient(ChannelType.JSON, results_callback)}.
            command_result_callback (Callable, optional): Callback for receiving data that are sent as a result of
                performing a control command (e.g. 5G-ERA Network Application state obtained by get-state command).
            command_error_callback (Callable, optional): Callback which is emitted when server failed to process the
                incoming control command.
            logging_level (int): Logging level.
            socketio_debug (bool): Socket.IO debug flag.
            stats (bool): Store output data sizes.
            back_pressure_size (int, optional): Back pressure size - max size of eio.queue.qsize().
            recreate_coder_attempts_count (int): How many times try to recreate the frame encoder/decoder.
            reconnection_attempts (int): How many times to try to reconnect if the connection to the server is lost.
            disconnect_on_unhandled (bool): Whether to call self.disconnect() if unhandled exception occurs.
        """

        # Create Socket.IO Client.
        self._sio = socketio.Client(
            logger=socketio_debug, reconnection_attempts=reconnection_attempts, handle_sigint=False, json=ujson
        )

        # Register connect, disconnect a connect error callbacks.
        self._sio.on("connect", self.data_connect_callback, namespace=DATA_NAMESPACE)
        self._sio.on("connect", self.control_connect_callback, namespace=CONTROL_NAMESPACE)
        self._sio.on("disconnect", self.data_disconnect_callback, namespace=DATA_NAMESPACE)
        self._sio.on("disconnect", self.control_disconnect_callback, namespace=CONTROL_NAMESPACE)
        self._sio.on("__disconnect_final", self.data_disconnect_final_callback, namespace=DATA_NAMESPACE)
        self._sio.on("__disconnect_final", self.control_disconnect_final_callback, namespace=CONTROL_NAMESPACE)
        self._sio.on("connect_error", self.data_connect_error_callback, namespace=DATA_NAMESPACE)
        self._sio.on("connect_error", self.control_connect_error_callback, namespace=CONTROL_NAMESPACE)

        # Register custom callbacks for command results and errors.
        self._sio.on(COMMAND_RESULT_EVENT, command_result_callback, namespace=CONTROL_NAMESPACE)
        self._sio.on(COMMAND_ERROR_EVENT, command_error_callback, namespace=CONTROL_NAMESPACE)

        # Create channels - custom callbacks and send functions including encoding.
        # NOTE: DATA_NAMESPACE is assumed to be or will be a connected namespace.
        self._channels = ClientChannels(
            self._sio,
            callbacks_info=callbacks_info,
            disconnect_callback=self.disconnect if disconnect_on_unhandled else None,
            back_pressure_size=back_pressure_size,
            recreate_coder_attempts_count=recreate_coder_attempts_count,
            stats=stats,
        )

        # Save custom command callbacks.
        self._command_result_callback = command_result_callback
        self._command_error_callback = command_error_callback

        # Set logger.
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging_level)

        # Init 5G-ERA Network Application address member.
        self.netapp_address: Union[str, None] = None

        # Substitute send function calls.
        self.send_image = self._channels.send_image
        self.send_data = self._channels.send_data

        # Args for registration.
        self._args: Optional[Dict[str, Any]] = None

    def register(
        self,
        netapp_address: str,
        args: Optional[Dict[str, Any]] = None,
        wait_until_available: bool = False,
        wait_timeout: int = -1,
    ) -> None:
        """Connects to the 5G-ERA Network Application server DATA_NAMESPACE and CONTROL_NAMESPACE.

        Args:
            netapp_address (str): The URL of the 5G-ERA Network Application server, including the scheme and optionally
                port and path to the interface, e.g. http://localhost:80 or http://gateway/path_to_interface.
            args (Dict, optional): Optional parameters to be passed to the 5G-ERA Network Application, in the form of
                dict. Defaults to None.
            wait_until_available: If True, the client will repeatedly try to register with the Network Application
                until it is available. Defaults to False.
            wait_timeout: How long the client will try to connect to network application. Only used if
                wait_until_available is True. If negative, the client will wait indefinitely. Defaults to -1.

        Raises:
            FailedToConnect: Failed to connect to network application exception.
            FailedToInitialize: Failed to initialize the network application.

        Returns:
            Response: response from the 5G-ERA Network Application.
        """

        # Store args for repeat registration.
        self._args = args
        # Connect to server
        self.netapp_address = netapp_address
        namespaces_to_connect = [DATA_NAMESPACE, CONTROL_NAMESPACE]
        start_time = time.time()
        while True:
            try:
                self.logger.info(f"Trying to connect to the network application: {netapp_address}")
                self._sio.connect(
                    netapp_address,
                    namespaces=namespaces_to_connect,
                    wait_timeout=10,
                )
                break
            except ConnectionError as ex:
                self.logger.debug(f"Failed to connect: {repr(ex)}")
                if not wait_until_available or (wait_timeout > 0 and start_time + wait_timeout < time.time()):
                    raise FailedToConnect(ex)
                self.logger.warning("Failed to connect to network application. Retrying in 1 second.")
                time.sleep(1)

        self.logger.info(f"Client connected to namespaces: {namespaces_to_connect}")

    def disconnect(self) -> None:
        """Disconnects the WebSocket connection."""

        if self._sio.connected:
            self._sio.disconnect()

    def print_stats(self):
        """Print stats info - transferred bytes."""

        if self._channels.stats:
            if len(self._channels.sizes) > 0:
                self.logger.info(
                    f"Transferred bytes sum: {sum(self._channels.sizes)} "
                    f"median: {statistics.median(self._channels.sizes):.3f} "
                    f"mean: {statistics.mean(self._channels.sizes):.3f} "
                    f"min: {min(self._channels.sizes)} "
                    f"max: {max(self._channels.sizes)} "
                )

    def wait(self) -> None:
        """Blocking infinite waiting."""

        self._sio.wait()

    def data_connect_callback(self) -> None:
        """The callback called once the connection to the 5G-ERA Network Application DATA_NAMESPACE is made."""

        self.logger.info(
            f"Connected to server {DATA_NAMESPACE}, eio_sid" f" {self._channels.get_client_eio_sid(DATA_NAMESPACE)}"
        )

    def control_connect_callback(self) -> None:
        """The callback called once the connection to the 5G-ERA Network Application CONTROL_NAMESPACE is made."""

        self.logger.info(
            f"Connected to server {CONTROL_NAMESPACE}, eio_sid "
            f"{self._channels.get_client_eio_sid(CONTROL_NAMESPACE)}"
        )

        # Initialize the network application with desired parameters using the init command.
        control_command = ControlCommand(ControlCmdType.INIT, clear_queue=False, data=self._args)
        self.logger.info(f"Initialize the network application using the init command {control_command}")
        initialized, message = self.send_control_command(control_command)
        if not initialized:
            raise FailedToInitialize(f"Failed to initialize the network application: {message}")

    def data_disconnect_callback(self) -> None:
        """The callback called once the connection to the 5G-ERA Network Application DATA_NAMESPACE is lost."""

        self.logger.info(
            f"Disconnected from server {DATA_NAMESPACE}, eio_sid "
            f"{self._channels.get_client_eio_sid(DATA_NAMESPACE)}"
        )
        self.disconnect()

    def data_disconnect_final_callback(self) -> None:
        """The callback called once the connection to the 5G-ERA Network Application DATA_NAMESPACE is lost."""

        self.logger.info(
            f"Finally disconnected from server {DATA_NAMESPACE}, eio_sid "
            f"{self._channels.get_client_eio_sid(DATA_NAMESPACE)}"
        )
        self.disconnect()
        self.print_stats()

    def control_disconnect_callback(self) -> None:
        """The callback called once the connection to the 5G-ERA Network Application CONTROL_NAMESPACE is lost."""

        self.logger.info(
            f"Disconnected from server {CONTROL_NAMESPACE}, eio_sid "
            f"{self._channels.get_client_eio_sid(CONTROL_NAMESPACE)}"
        )
        self.disconnect()

    def control_disconnect_final_callback(self) -> None:
        """The callback called once the connection to the 5G-ERA Network Application CONTROL_NAMESPACE is lost."""

        self.logger.info(
            f"Finally disconnected from server {CONTROL_NAMESPACE}, eio_sid "
            f"{self._channels.get_client_eio_sid(CONTROL_NAMESPACE)}"
        )
        self.disconnect()

    def data_connect_error_callback(self, message: Optional[str] = None) -> None:
        """The callback called on connection DATA_NAMESPACE error.

        Args:
            message (str, optional): Error message.
        """

        self.logger.error(
            f"Connection {DATA_NAMESPACE} error: {message}, eio_sid "
            f"{self._channels.get_client_eio_sid(DATA_NAMESPACE)}"
        )

    def control_connect_error_callback(self, message: Optional[str] = None) -> None:
        """The callback called on connection CONTROL_NAMESPACE error.

        Args:
            message (str, optional): Error message.
        """

        self.logger.error(
            f"Connection {CONTROL_NAMESPACE} error: {message}, eio_sid "
            f"{self._channels.get_client_eio_sid(CONTROL_NAMESPACE)}"
        )

    def send_control_command(self, control_command: ControlCommand) -> Tuple[bool, str]:
        """Sends control command over the websocket.

        Args:
            control_command (ControlCommand): Control command to be sent.

        Returns:
            (success (bool), message (str)): If False, command failed.
        """

        if self._sio.eio.state == "connected":
            command_result: Tuple[bool, str] = self._sio.call(COMMAND_EVENT, asdict(control_command), CONTROL_NAMESPACE)
            return command_result
        else:
            raise ConnectionError("Client is not connected to server.")
