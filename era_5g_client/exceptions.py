class Era5gClientException(Exception):
    """Common base for all exception that this client might raise."""

    pass


class FailedToConnect(Era5gClientException):
    """Exception which is raised when the client could not connect to the
    NetApp or Middleware."""

    pass


class FailedToObtainPlan(Era5gClientException):
    """Exception which is raised when the client could not get the plan from
    the Middleware."""

    pass


class NetAppNotReady(Era5gClientException):
    """Raised when an operation was requested on NetApp which is not ready."""


class FailedToSendData(Era5gClientException):
    """Raised when the data could not be send."""
