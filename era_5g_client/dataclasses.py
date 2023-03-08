from dataclasses import dataclass


@dataclass
class MiddlewareInfo:
    uri: str
    user_id: str
    password: str

    def build_api_endpoint(self, path: str) -> str:
        """Builds an API endpoint on the NetApp interface.

        Args:
            path (str): endpoint path
        Returns:
            _type_: complete URI to requested endpoint
        """

        return f"http://{self.uri}/{path}"


@dataclass
class NetAppLocation:
    uri: str
    port: int

    def build_api_endpoint(self, path: str) -> str:
        """Builds an API endpoint on the NetApp interface.

        Args:
            path (str): endpoint path
        Returns:
            _type_: complete URI to requested endpoint
        """

        return f"http://{self.uri}:{self.port}/{path}"
