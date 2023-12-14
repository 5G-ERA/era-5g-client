import logging
import socket
from contextlib import closing
from threading import Event, Thread
from typing import Any, Dict, Tuple

import pytest
import socketio
from flask import Flask

from era_5g_client.client_base import NetAppClientBase
from era_5g_interface.channels import COMMAND_EVENT, CONTROL_NAMESPACE, DATA_NAMESPACE, CallbackInfoClient, ChannelType
from era_5g_interface.exceptions import BackPressureException


def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


port = find_free_port()


def test_client_send_data() -> None:
    got_data = Event()

    def json_callback_websocket(sid: str, data: Dict[str, Any]) -> None:
        got_data.set()

    def control_callback_websocket(sid: str, data: Dict[str, Any]) -> Tuple[bool, str]:
        return True, "OK"

    def connect_callback_websocket(sid: str, environ: Dict) -> None:
        pass

    def get_results(results: Dict[str, Any]) -> None:
        pass

    def thread_flask() -> None:
        sio = socketio.Server()

        sio.on("json", json_callback_websocket, namespace=DATA_NAMESPACE)
        sio.on(COMMAND_EVENT, control_callback_websocket, namespace=CONTROL_NAMESPACE)
        sio.on("connect", connect_callback_websocket, namespace=DATA_NAMESPACE)

        app = Flask(__name__)
        app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)  # type: ignore

        logging.getLogger().info("Starting Flask...")
        app.run(port=port, host="0.0.0.0")

    t = Thread(target=thread_flask)
    t.daemon = True
    t.start()

    with pytest.raises(ValueError, match="Invalid value for back_pressure_size."):
        NetAppClientBase(
            callbacks_info={"results": CallbackInfoClient(ChannelType.JSON, get_results)}, back_pressure_size=0
        )

    client = NetAppClientBase(
        callbacks_info={"results": CallbackInfoClient(ChannelType.JSON, get_results)}, back_pressure_size=2
    )

    client.register(f"http://localhost:{port}", wait_until_available=True, wait_timeout=5)

    with pytest.raises(BackPressureException):  # noqa:PT012
        for _ in range(100):
            client.send_data({"test": "test"}, "json", can_be_dropped=True)

    assert got_data.wait(5), "5G-ERA Network Application didn't get json..."
