import logging
from enum import Enum
from typing import Any, Callable, Dict, Optional

import requests
from requests import HTTPError

from era_5g_client.client_base import NetAppClientBase
from era_5g_client.dataclasses import MiddlewareInfo
from era_5g_client.exceptions import FailedToConnect, FailedToDeleteResource, FailedToObtainPlan, NetAppNotReady
from era_5g_client.middleware_resource_checker import MiddlewareResourceChecker
from era_5g_interface.channels import CallbackInfoClient


class RunTaskMode(Enum):
    """Run task mode."""

    # Deploy the task but don't wait until it is ready, do not register with it.
    DO_NOTHING = 1
    # Wait until the 5G-ERA Network Application is ready, do not register with it.
    WAIT = 2
    # Wait until the 5G-ERA Network Application is ready and register with it afterward.
    WAIT_AND_REGISTER = 3


class NetAppClient(NetAppClientBase):
    """Extension of the NetAppClientBase class, which enable communication with the Middleware.

    It allows to deploy the 5G-ERA Network Application and check on the status of the 5G-ERA Network Application.
    """

    def __init__(
        self,
        callbacks_info=Dict[str, CallbackInfoClient],
        command_result_callback: Optional[Callable] = None,
        command_error_callback: Optional[Callable] = None,
        logging_level: int = logging.INFO,
        socketio_debug: bool = False,
        stats: bool = False,
        back_pressure_size: int = 5,
        recreate_h264_attempts_count: int = 5,
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
            back_pressure_size (int): Back pressure size - max size of eio.queue.qsize().
            recreate_h264_attempts_count (int): How many times try to recreate the H.264 encoder/decoder.
        """

        super().__init__(
            callbacks_info,
            command_result_callback,
            command_error_callback,
            logging_level,
            socketio_debug,
            stats,
            back_pressure_size,
            recreate_h264_attempts_count,
        )

        self.host: Optional[str] = None
        self.action_plan_id: Optional[str] = None
        self.resource_checker: Optional[MiddlewareResourceChecker] = None
        self.middleware_info: Optional[MiddlewareInfo] = None
        self.token: Optional[str] = None

    def connect_to_middleware(self, middleware_info: MiddlewareInfo) -> None:
        """Authenticates with the middleware and obtains a token for future calls.

        Args:
            middleware_info (MiddlewareInfo): Middleware info, i.e. dataclass with address, user's id and password.

        Raises:
            FailedToConnect: Raised when the authentication with the middleware failed.
        """

        self.middleware_info = middleware_info
        self.middleware_info.address = self.middleware_info.address.rstrip("/")
        try:
            # Connect to the middleware.
            self.token = self.gateway_login(self.middleware_info.user_id, self.middleware_info.password)
        except FailedToConnect as ex:
            self.logger.error(f"Can't connect to middleware: {ex}")
            raise

    def run_task(
        self,
        task_id: str,
        robot_id: str,
        resource_lock: bool,
        mode: RunTaskMode = RunTaskMode.WAIT_AND_REGISTER,
        args: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Deploys the task with provided *task_id* using middleware and (optionally) waits until the 5G-ERA Network
        Application is ready and register with it.

        Args:
            task_id (str): The GUID of the task which should be deployed.
            robot_id (str): The GUID of the robot that deploys the 5G-ERA Network Application.
            resource_lock (bool): TBA.
            mode (RunTaskMode): Specify the mode in which the run_task works.
            args (Dict[str, Any], optional): 5G-ERA Network Application specific arguments. Applied only if register
                is True. Defaults to None.

        Raises:
            FailedToObtainPlan: Raised when could not get the plan.
            FailedToConnect: Raised when running the task failed.
        """

        assert self.middleware_info
        try:
            self.action_plan_id = self.gateway_get_plan(
                task_id, resource_lock, robot_id
            )  # Get the plan_id by sending the token and task_id.
            if not self.action_plan_id:
                raise FailedToObtainPlan("Failed to obtain action plan id...")

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
        args: Optional[Dict[str, Any]] = None,
        wait_until_available: bool = False,
        wait_timeout: int = -1,
    ) -> None:
        """Calls the /register endpoint of the 5G-ERA Network Application interface and if the registration is
        successful, it sets up the WebSocket connection for results retrieval.

        Args:
            netapp_address (str): The URL of the network application interface, including the scheme and optionally
                port and path to the interface, e.g. http://localhost:80 or http://gateway/path_to_interface.
            args (Dict[str, Any], optional): 5G-ERA Network Application specific arguments. Defaults to None.
            wait_until_available: If True, the client will repeatedly try to register with the Network Application
                until it is available. Defaults to False.
            wait_timeout: How long the client will try to connect to network application. Only used if
                wait_until_available is True. If negative, the client will wait indefinitely. Defaults to -1.

        Raises:
            NetAppNotReady: Raised when register called before the 5G-ERA Network Application is ready.
        """

        if not self.resource_checker:
            raise NetAppNotReady("Not connected to the middleware.")

        if not self.resource_checker.is_ready():
            raise NetAppNotReady("Not ready.")

        super().register(netapp_address, args, wait_until_available, wait_timeout)

    def disconnect(self) -> None:
        """Disconnects the WebSocket connection, stop resource checker and delete resources."""

        super().disconnect()
        if self.resource_checker is not None:
            self.resource_checker.stop()
        self.delete_all_resources()

    def wait_until_netapp_ready(self) -> None:
        """Blocking wait until the 5G-ERA Network Application is running.

        Raises:
            FailedToConnect: Raised when resource_checker si None.
        """
        if not self.resource_checker:
            raise FailedToConnect("Not connected to middleware.")
        self.resource_checker.wait_until_resource_ready()

    def load_netapp_address(self) -> None:
        """Load 5G-ERA Network Application address.

        Raises:
            NetAppNotReady: Raised when resource_checker si None or not ready.
        """

        if not (self.resource_checker and self.resource_checker.is_ready()):
            raise NetAppNotReady
        # TODO: check somehow that the url is correct?
        self.netapp_address = str(self.resource_checker.url)

    def gateway_login(self, user_id: str, password: str) -> str:
        """Login to gateway.

        Args:
            user_id (str): User ID.
            password (str): Password.

        Returns:
            Token.

        Raises:
            FailedToConnect: Raised when could not log in to the middleware gateway.
        """

        assert self.middleware_info
        self.logger.debug("Trying to log into the middleware")
        # Request Login.
        try:
            r = requests.post(
                self.middleware_info.build_api_endpoint("Login"), json={"Id": user_id, "Password": password}
            )
            response = r.json()
            if "errors" in response:
                raise FailedToConnect(str(response["errors"]))
            new_token = response["token"]  # Token is stored here.
            # time.sleep(10)
            if not isinstance(new_token, str) or not new_token:
                raise FailedToConnect("Invalid token.")
            return new_token

        except requests.HTTPError as e:
            if e.response:
                raise FailedToConnect(
                    f"Could not login to the middleware gateway, status code:" f" {e.response.status_code}"
                )
            else:
                raise FailedToConnect(f"Could not login to the middleware gateway, status code: {e}")
        except KeyError as e:
            raise FailedToConnect(f"Could not login to the middleware gateway, the response does not contain {e}")

    def gateway_get_plan(self, taskid: str, resource_lock: bool, robot_id: str) -> str:
        """Get task action plan ID from middleware.

        Args:
            taskid (str): Task ID.
            resource_lock (bool): Resource lock.
            robot_id (str): Robot ID.

        Returns:
            Action plan ID.
        Raises:
            FailedToConnect: Raised when could not get the plan.
        """

        assert self.middleware_info
        # Request plan.
        try:
            self.logger.debug("Goal task is: " + str(taskid))
            hed = {"Authorization": f"Bearer {str(self.token)}"}
            data = {
                "TaskId": str(taskid),
                "LockResourceReUse": resource_lock,
                "RobotId": robot_id,
            }
            r = requests.post(self.middleware_info.build_api_endpoint("Task/Plan"), json=data, headers=hed)
            response = r.json()

            if not isinstance(response, Dict):
                raise FailedToConnect("Invalid response.")

            if "statusCode" in response and (response["statusCode"] == 500 or response["statusCode"] == 400):
                raise FailedToConnect(f"response {response['statusCode']}: {response['message']}")
            # TODO: if "errors" in response:
            #           raise FailedToConnect(str(response["errors"]))
            action_plan_id = str(response["ActionPlanId"])
            self.logger.debug("ActionPlanId ** is: " + str(action_plan_id))
            return action_plan_id
        except KeyError as e:
            raise FailedToObtainPlan(f"Could not get the plan: {e}")

    def delete_all_resources(self) -> None:
        """Delete all resources.

        Returns:
            None

        Raises:
            FailedToConnect: Raised when could not delete the resource.
        """

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
            if e.response:
                self.logger.debug(e.response.status_code)
            else:
                self.logger.debug(e)
            raise FailedToDeleteResource(
                f"Error, could not delete the resource, revisit the log files for more details. {e}"
            )

    def delete_single_resource(self) -> None:
        """Delete single resource - not implemented."""

        raise NotImplementedError  # TODO: implement

    def gateway_log_off(self) -> None:
        """Gateway log off - not implemented."""

        self.logger.debug("Middleware log out successful")
        # TODO: implement
        pass
