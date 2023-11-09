import logging
import socket
import time
from contextlib import closing
from threading import Thread
from typing import Any, Dict

import pytest
import socketio
from flask import Flask

from era_5g_client.client_base import NetAppClientBase
from era_5g_client.exceptions import BackPressureException


def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


port = find_free_port()
got_data = False


def test_client_send_data() -> None:
    def json_callback_websocket(self, data: Dict[str, Any]):
        global got_data
        got_data = True

    def control_callback_websocket(self, data: Dict[str, Any]):
        pass

    def results_callback_websocket(self, data: Dict[str, Any]):
        pass

    def get_results(results: Dict[str, Any]) -> None:
        pass

    def thread_flask() -> None:
        sio = socketio.Server()
        sio.on("json", json_callback_websocket, namespace="/data")
        sio.on("command", control_callback_websocket, namespace="/control")
        sio.on("connect", results_callback_websocket, namespace="/results")

        app = Flask(__name__)
        app.wsgi_app = socketio.WSGIApp(sio, app.wsgi_app)  # type: ignore

        logging.getLogger().info("Starting Flask...")
        app.run(port=port, host="0.0.0.0")

    t = Thread(target=thread_flask)
    t.daemon = True
    t.start()

    with pytest.raises(ValueError, match="Invalid value for back_pressure_size."):
        NetAppClientBase(get_results, back_pressure_size=0)

    client = NetAppClientBase(get_results, back_pressure_size=2)

    client.register(f"http://localhost:{port}", wait_until_available=True, wait_timeout=5)

    with pytest.raises(BackPressureException):  # noqa:PT012
        for _ in range(100):
            client.send_json_ws({"test": "test"})

    for _ in range(10):
        if got_data:
            break
        time.sleep(1)
    else:
        raise Exception("NetApp didn't get json...")
