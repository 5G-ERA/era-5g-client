from dataclasses import dataclass
from dacite import from_dict

@dataclass
class MiddlewareInfo:
    # The IP or hostname of the middleware
    address: str
    # The middleware user's id
    user_id: str
    # The middleware user's password
    password: str

    def build_api_endpoint(self, path: str) -> str:
        """Builds an API endpoint on the middleware.

        Args:
            path (str): endpoint path
        Returns:
            _type_: complete URI to requested endpoint
        """

        return f"http://{self.address}/{path}"

@dataclass
class MiddlewareRosTopicModel:
    # Name of the topic
    name: str
    # Type of the topic message
    type: str
    # Description of the topic
    description: str
    # Is currently been used by the robot
    enabled: bool

    def build_api_endpoint(self, path: str) -> str:
        """Builds an API endpoint on the middleware.

        Args:
            path (str): endpoint path
        Returns:
            _type_: complete URI to requested endpoint
        """

        return f"http://{self.address}/{path}"

@dataclass
class MiddlewareServiceInfo:
    # The unique identifier of the service
    id: str
    # The name of the service
    name: str
    # Service instance id
    serviceInstanceId: str
    # Service type
    ServiceType: str
    # Is the service reusable
    isReusable: bool
    # Desired status of the service
    desiredStatus: str
    # URL of the servie
    serviceUrl: str
    # published topics by network application
    rosTopicsPub: list[MiddlewareRosTopicModel]
    # subcribed topics by network application
    rosTopicsSub: list[MiddlewareRosTopicModel]
    # Version of ROS
    rosVersion: int
    # ROS distribution
    rosDistro: str
    # Tags for the network application
    tags: list
    # Instance family
    instanceFamily: str
    # Success rate of network application
    successRate: int
    # Status of the service
    serviceStatus: str
    # Container image
    containerImage: None
    # Min ram to run netapp
    minimunRam: int
    # Min number of cores
    minimumNumCores: int
    # Onboarded time for network application.
    onboardedTime: str

    def build_api_endpoint(self, path: str) -> str:
        """Builds an API endpoint on the middleware.

        Args:
            path (str): endpoint path
        Returns:
            _type_: complete URI to requested endpoint
        """

        return f"http://{self.address}/{path}"

@dataclass
class MiddlewareActionInfo:
    # The unique identifier of the action
    id: str
    # The name of the action
    action: str
    # tags of the action
    tags: list
    # Order of the action
    order: int
    # Placement location
    placement: str
    # Type of placement
    placementType: str
    # priority of the action
    actionPriority: str
    # Status of the action
    actionStatus: str
    # Services of the action
    services : list[MiddlewareServiceInfo]

    def build_api_endpoint(self, path: str) -> str:
        """Builds an API endpoint on the middleware.

        Args:
            path (str): endpoint path
        Returns:
            _type_: complete URI to requested endpoint
        """

        return f"http://{self.address}/{path}"

@dataclass
class MiddlewarePlanInfo:
    # The unique identifier of the plan
    id: str
    # The unique identifier for the task
    taskId: str
    # The name of the task
    name: str
    # The status of the plan
    status: str
    # Check if the current plan is a replan.
    isReplan: bool
    # The last time the plan was modified
    lastStatusChange: str
    # List of actions in the task
    actionSequence: list[MiddlewareActionInfo]
    # robot id
    robotId: str
    # Time of task started.
    taskStartedAt: str

    def build_api_endpoint(self, path: str) -> str:
        """Builds an API endpoint on the middleware.

        Args:
            path (str): endpoint path
        Returns:
            _type_: complete URI to requested endpoint
        """

        return f"http://{self.address}/{path}"

@dataclass
class NetAppLocation:
    # The IP or hostname of the NetApp interface
    address: str
    # The port of the NetApp interface
    port: int

    def build_api_endpoint(self, path: str) -> str:
        """Builds an API endpoint on the NetApp interface.

        Args:
            path (str): endpoint path
        Returns:
            _type_: complete URI to requested endpoint
        """

        return f"http://{self.address}:{self.port}/{path}"
