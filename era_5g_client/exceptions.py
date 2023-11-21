class Era5gClientException(Exception):
    """Common base for all exception that this client might raise."""

    pass


class FailedToConnect(Era5gClientException):
    """Exception which is raised when the client could not connect to the 5G-ERA Network Application or Middleware."""

    pass


class FailedToInitialize(Era5gClientException):
    """Exception which is raised when the client could not initialize the 5G-ERA Network Application."""

    pass


class FailedToObtainPlan(Era5gClientException):
    """Exception which is raised when the client could not get the plan from the Middleware."""

    pass


class FailedToDeleteResource(Era5gClientException):
    """Exception which is raised when the client could not when could not delete Middleware resource."""

    pass


class NetAppNotReady(Era5gClientException):
    """Raised when an operation was requested on 5G-ERA Network Application which is not ready."""

    pass
