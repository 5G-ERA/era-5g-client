import logging
import time
from threading import Event, Thread
from typing import Callable, Dict, Optional

import requests
from requests import HTTPError

from era_5g_client.exceptions import FailedToConnect

logger = logging.getLogger(__name__)


class MiddlewareResourceChecker(Thread):
    """Class for checking Middleware resources."""

    def __init__(
        self,
        token: str,
        action_plan_id: str,
        status_endpoint: str,
        url_changed_callback: Optional[Callable] = None,
        **kw,
    ) -> None:
        """Constructor.

        Args:
            token (str): Login token.
            action_plan_id (str): Action plan ID.
            status_endpoint (str): Status endpoint.
            url_changed_callback (Callable, optional): Triggered if the received URL has changed.
            **kw: Thread arguments.
        """

        super().__init__(**kw)
        self.stop_event = Event()
        self.token = token
        self.action_plan_id = action_plan_id
        self.resource_state: Optional[Dict] = None
        self.url_changed_callback = url_changed_callback
        self.status_endpoint = status_endpoint
        self.status: Optional[str] = None  # TODO define as enum?
        self.url: Optional[str] = None

    def stop(self) -> None:
        """Stop thread."""

        self.stop_event.set()

    def run(self) -> None:
        """Run thread.

        Check resource status in loop.
        """

        while not self.stop_event.is_set():
            resource_state = self.get_resource_status()
            seq = resource_state.get("actionSequence", [])
            if seq:
                services = seq[0].get("Services", [])
                if services:
                    self.resource_state = services[0]
                    assert isinstance(self.resource_state, dict)
                    self.status = self.resource_state.get("serviceStatus", None)
                    old_url = self.url
                    self.url = self.resource_state.get("serviceUrl", None)
                    if old_url and self.url_changed_callback and old_url != self.url:
                        self.url_changed_callback()
                    logger.debug(f"{self.status=}, {self.url=}")
            time.sleep(0.5)  # TODO: adjust or use something similar to rospy.rate.sleep()

    def get_resource_status(self) -> Dict:
        """Get resource status.

        Returns:
            resource status in dictionary.
        """

        hed = {"Authorization": "Bearer " + str(self.token)}
        url = f"{self.status_endpoint}/{str(self.action_plan_id)}"

        try:  # Query orchestrator for latest information regarding the status of resources.
            response = requests.get(url, headers=hed)
        except HTTPError as e:
            if e.response:
                logger.debug(e.response.status_code)
            else:
                logger.debug(e)
            raise FailedToConnect(f"Could not get the resource status, revisit the log files for more details. {e}")
        resp = response.json()
        if isinstance(resp, dict):
            return resp
        else:
            raise FailedToConnect("Invalid response.")

    def wait_until_resource_ready(self, timeout: int = -1) -> None:
        """Wait until resource is ready.

        Args:
            timeout (int): Timeout - unused.
        """

        while not self.stop_event.is_set():
            # if timeout < 0 and time.time() < timeout:
            #    raise TimeoutError

            if self.is_ready():
                return
            time.sleep(0.1)

    def is_ready(self) -> bool:
        """Is resource ready?

        Returns:
            Ready status.
        """

        return self.status == "Active"
