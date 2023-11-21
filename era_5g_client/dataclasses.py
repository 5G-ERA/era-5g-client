from dataclasses import dataclass


@dataclass
class MiddlewareInfo:
    """Middleware info class."""

    # The IP or hostname of the middleware.
    address: str
    # The middleware user's ID.
    user_id: str
    # The middleware user's password.
    password: str

    def build_api_endpoint(self, path: str) -> str:
        """Builds an API endpoint on the middleware.

        Args:
            path (str): Endpoint path.
        Returns:
            str: Complete URI to requested endpoint.
        """

        return f"http://{self.address}/{path}"
