import logging
import time
from threading import Event, Thread
from typing import Callable, Dict, Optional

import requests
from requests import HTTPError

from era_5g_client.exceptions import FailedToConnect


class MiddlewareResourceChecker(Thread):
    def __init__(
        self, token: str, action_plan_id: str, status_endpoint: str, state_callback: Optional[Callable] = None, **kw
    ) -> None:
        super().__init__(**kw)
        self.stop_event = Event()
        self.token = token
        self.action_plan_id = action_plan_id
        self.resource_state: Optional[Dict] = None
        self.state_callback = state_callback
        self.status_endpoint = status_endpoint
        self.status: Optional[str] = None  # TODO define as enum?
        self.url: Optional[str] = None

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        while not self.stop_event.is_set():
            resource_state = self.get_resource_status()

            seq = resource_state.get("actionSequence", [])
            if seq:
                services = seq[0].get("Services", [])
                if services:
                    self.resource_state = services[0]
                    assert isinstance(self.resource_state, dict)
                    self.status = self.resource_state.get("serviceStatus", None)
                    self.url = self.resource_state.get("serviceUrl", None)
                    logging.debug(f"{self.status=}, {self.url=}")
            if self.state_callback:
                self.state_callback(self.resource_state)
            time.sleep(0.5)  # TODO: adjust or use something similar to rospy.rate.sleep()

    def get_resource_status(self) -> Dict:
        try:  # query orchestrator for latest information regarding the status of resources.
            hed = {"Authorization": "Bearer " + str(self.token)}
            url = f"{self.status_endpoint}/{str(self.action_plan_id)}"
            response = requests.get(url, headers=hed)
            resp = response.json()
            if isinstance(resp, dict):
                return resp
            else:
                raise FailedToConnect("Invalid response.")

        except HTTPError as e:
            print(e.response.status_code)
            raise FailedToConnect("Could not get the resource status, revisit the log files for more details.")

    def wait_until_resource_ready(self, timeout: int = -1) -> None:
        while not self.stop_event.is_set():
            # if timeout < 0 and time.time() < timeout:
            #    raise TimeoutError

            if self.is_ready():
                return
            time.sleep(0.1)

    def is_ready(self) -> bool:
        return self.status == "Active"
