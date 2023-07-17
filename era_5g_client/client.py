import logging
import os
from collections.abc import Callable
from enum import Enum
from typing import Dict, Optional

import requests
from requests import HTTPError

from era_5g_client.client_base import NetAppClientBase
from era_5g_client.dataclasses import MiddlewareInfo
from era_5g_client.exceptions import FailedToConnect, NetAppNotReady
from era_5g_client.middleware_resource_checker import MiddlewareResourceChecker

# port of the netapp's server
NETAPP_PORT = int(os.getenv("NETAPP_PORT", 5896))


class RunTaskMode(Enum):
    # deploy the task but don't wait until it is ready, do not register with it
    DO_NOTHING = 1
    # wait until the netapp is ready, do not register with it
    WAIT = 2
    # wait until the netapp is ready and register with it afterwards
    WAIT_AND_REGISTER = 3


class NetAppClient(NetAppClientBase):
    """Extension of the NetAppClientBase class, which enable communication with
    the Middleware.

    It allows to deploy the NetApp and check on the status of the NetApp
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
            control_cmd_error_event (Callable, optional): Callback which is emited when
                server failed to process the incoming control command.

        Raises:
            FailedToConnect: When connection to the middleware could not be set or
                login failed
            FailedToObtainPlan: When the plan was not successfully returned from
                the middleware
        """

        super().__init__(
            results_event,
            image_error_event,
            json_error_event,
            control_cmd_event,
            control_cmd_error_event,
            logging_level,
            socketio_debug,
        )

        self.host: Optional[str] = None
        self.action_plan_id: Optional[str] = None
        self.resource_checker: Optional[MiddlewareResourceChecker] = None
        self.middleware_info: Optional[MiddlewareInfo] = None
        self.token: Optional[str] = None

    def connect_to_middleware(self, middleware_info: MiddlewareInfo) -> None:
        """Authenticates with the middleware and obtains a token for future
        calls.

        Args:
            middleware_info (MiddlewareInfo): Middleware info, i.e. dataclass with address, user's id and password

        Raises:
            FailedToConnect: Raised when the authentication with the
                middleware failed
        """
        self.middleware_info = middleware_info
        self.middleware_info.address = self.middleware_info.address.rstrip("/")
        try:
            # connect to the middleware
            self.token = self.gateway_login(self.middleware_info.user_id, self.middleware_info.password)
        except FailedToConnect as ex:
            self.logger.error(f"Can't connect to middleware: {ex}")
            raise

    def run_task(
        self,
        task_id: str,
        robot_id: str,
        resource_lock: bool,
        mode: Optional[RunTaskMode] = RunTaskMode.WAIT_AND_REGISTER,
        args: Optional[Dict] = None,
    ) -> None:
        """Deploys the task with provided *task_id* using middleware and
        (optionally) waits until the netapp is ready and register with it.

        Args:
            task_id (str): The GUID of the task which should be deployed.
            robot_id (str): The GUID of the robot that deploys the NetApp.
            resource_lock (bool): TBA
            mode (Optional[RunTaskMode]): Specify the mode in which the run_task
                works
            args (Optional[Dict], optional): NetApp-specific arguments. Applied only if register
                is True. Defaults to None.

        Raises:
            FailedToConnect: Raised when running the task failed.
        """
        assert self.middleware_info
        try:
            self.action_plan_id = self.gateway_get_plan(
                task_id, resource_lock, robot_id
            )  # Get the plan_id by sending the token and task_id
            if not self.action_plan_id:
                raise FailedToConnect("Failed to obtain action plan id...")

            self.resource_checker = MiddlewareResourceChecker(
                str(self.token),
                self.action_plan_id,
                self.middleware_info.build_api_endpoint("orchestrate/orchestrate/plan"),
                daemon=True,
            )

            self.resource_checker.start()
            if mode in [RunTaskMode.WAIT, RunTaskMode.WAIT_AND_REGISTER]:
                self.wait_until_netapp_ready()
                self.load_netapp_address()
                if not self.netapp_address:
                    raise FailedToConnect("Failed to obtain network application address")
                if mode == RunTaskMode.WAIT_AND_REGISTER:
                    self.register(self.netapp_address, args, wait_until_available=True)
        except (FailedToConnect, NetAppNotReady) as ex:
            self.delete_all_resources()
            self.logger.error(f"Failed to run task: {ex}")
            raise

    def register(
        self,
        netapp_address: str,
        args: Optional[Dict] = None,
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
            args (Optional[Dict], optional): NetApp-specific arguments. Defaults to None.
            wait_until_available: If True, the client will repeatedly try to register
                with the Network Application until it is available. Defaults to False.
            wait_timeout: How long the client will try to connect to network application.
                Only used if wait_until_available is True. If negative, the client
                will waits indefinitely. Defaults to -1.

        Raises:
            NetAppNotReady: Raised when register called before the NetApp is ready.

        Returns:
            Response: The response from the NetApp.
        """
        if not self.resource_checker:
            raise NetAppNotReady("Not connected to the middleware.")

        if not self.resource_checker.is_ready():
            raise NetAppNotReady("Not ready.")

        super().register(netapp_address, args, wait_until_available, wait_timeout)

    def disconnect(self) -> None:
        """Calls the /unregister endpoint of the server and disconnects the
        WebSocket connection."""
        super().disconnect()
        if self.resource_checker is not None:
            self.resource_checker.stop()
        self.delete_all_resources()

    def wait_until_netapp_ready(self) -> None:
        """Blocking wait until the NetApp is running.

        Raises:
            NetAppNotReady: _description_
        """
        if not self.resource_checker:
            raise FailedToConnect("Not connected to middleware.")
        self.resource_checker.wait_until_resource_ready()

    def load_netapp_address(self) -> None:
        if not (self.resource_checker and self.resource_checker.is_ready()):
            raise NetAppNotReady
        # TODO: check somehow that the url is correct?
        self.netapp_address = str(self.resource_checker.url)

    def gateway_login(self, user_id: str, password: str) -> str:
        assert self.middleware_info
        self.logger.debug("Trying to log into the middleware")
        # Request Login
        try:
            r = requests.post(
                self.middleware_info.build_api_endpoint("Login"), json={"Id": user_id, "Password": password}
            )
            response = r.json()
            if "errors" in response:
                raise FailedToConnect(str(response["errors"]))
            new_token = response["token"]  # Token is stored here
            # time.sleep(10)
            if not isinstance(new_token, str) or not new_token:
                raise FailedToConnect("Invalid token.")
            return new_token

        except requests.HTTPError as e:
            raise FailedToConnect(f"Could not login to the middleware gateway, status code: {e.response.status_code}")
        except KeyError as e:
            raise FailedToConnect(f"Could not login to the middleware gateway, the response does not contain {e}")

    def gateway_get_plan(self, taskid: str, resource_lock: bool, robot_id: str) -> str:
        assert self.middleware_info
        # Request plan

        try:
            self.logger.debug("Goal task is: " + str(taskid))
            hed = {"Authorization": f"Bearer {str(self.token)}"}
            data = {
                "TaskId": str(taskid),
                "LockResourceReUse": resource_lock,
                "RobotId": robot_id,
            }
            response = requests.post(
                self.middleware_info.build_api_endpoint("Task/Plan"), json=data, headers=hed
            ).json()
            if not isinstance(response, dict):
                raise FailedToConnect("Invalid response.")

            if "statusCode" in response and (response["statusCode"] == 500 or response["statusCode"] == 400):
                raise FailedToConnect(f"response {response['statusCode']}: {response['message']}")
            # todo:             if "errors" in response:
            #                 raise FailedToConnect(str(response["errors"]))
            action_plan_id = str(response["ActionPlanId"])
            self.logger.debug("ActionPlanId ** is: " + str(action_plan_id))
            return action_plan_id
        except KeyError as e:
            raise FailedToConnect(f"Could not get the plan: {e}")

    def delete_all_resources(self) -> None:
        if self.token is None or self.action_plan_id is None:
            return

        try:
            hed = {"Authorization": "Bearer " + str(self.token)}
            if self.middleware_info:
                url = self.middleware_info.build_api_endpoint(
                    f"orchestrate/orchestrate/plan/{str(self.action_plan_id)}"
                )
                response = requests.delete(url, headers=hed)

                if response.ok:
                    self.logger.debug("Resource deleted")

        except HTTPError as e:
            self.logger.debug(e.response.status_code)
            raise FailedToConnect("Error, could not get delete the resource, revisit the log files for more details.")

    def delete_single_resource(self) -> None:
        raise NotImplementedError  # TODO

    def gateway_log_off(self) -> None:
        self.logger.debug("Middleware log out successful")
        # TODO
        pass
