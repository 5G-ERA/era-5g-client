# era-5g-client

A client application for 5G-ERA Network Applications. Contains the basic implementation of the client ([client.py](era_5g_client/client.py)).

## Related Repositories

- [era-5g-interface](https://github.com/5G-ERA/era-5g-interface) - python interface (support classes) for Network 
  Applications.
- [era-5g-server](https://github.com/5G-ERA/era-5g-server) - server classes for 5G-ERA Network Applications with 
  various transport options.
- [Reference-NetApp](https://github.com/5G-ERA/Reference-NetApp) - reference 5G-ERA Network Application implementation
  with MMCV detector.
- 
## Installation

The package could be installed via pip:

```bash
pip install era_5g_client
```

## Examples

Two example clients (reference implementations) are provided to test the 5G-ERA Network Application.

System environment variables can be set, e.g.:
```
# Use video file
export FROM_SOURCE=False
export TEST_VIDEO_FILE=whatever_video.mp4
```
or
```
# Use webcam
export FROM_SOURCE=True
```

### Using middleware ([examples/client.py](examples/client.py))

The first example uses middleware to deploy the 5G-ERA Network Application and to handle its life cycle. 
Therefore, the 5G-ERA Network Application needs to be uploaded to the accessible docker repository and the 5G-ERA 
Network Application needs to be registered within the middleware. Basic configuration needs to be provided:

System environment variables that should be set:

```
# ip address or hostname of the computer, where the middleware runs
export MIDDLEWARE_ADDRESS=middleware_address
# the GUID of the registered middleware user
export MIDDLEWARE_USER=middleware_user
the password of the registered middleware user
export MIDDLEWARE_PASSWORD=middleware_password
the middleware GUID of the task that should be initialized
export MIDDLEWARE_TASK_ID=middleware_task_id
```

The user and password could be registered with the **/register** endpoint on the middleware 
(using Postman for example).

```bash
python3 client.py
```

### Avoiding middleware ([examples/client_no_middleware.py](examples/client_no_middleware.py))

For local testing, the middleware could be avoided, so the 5G-ERA Network Application needs to be started manually. 
Basic configuration needs to be provided:

System environment variables that can be set, e.g.:

```
# ip address or hostname and port (default is 5896) of the computer, where the 5G-ERA Network Application is deployed
export NETAPP_ADDRESS=http://localhost:5896
```

```bash
python3 client_no_middleware.py
```

## Classes

### NetAppClient ([client.py](era_5g_client/client.py))

Basic implementation of the client. Allows to register with the 5G-ERA Network Application and set the websocket-based 
communication for reading of results.

It creates websocket connection and bind callbacks from the 5G-ERA Network Application.

How to send data? E.g.:

        client.send_image(frame, "image", ChannelType.H264, timestamp, encoding_options=h264_options)
        client.send_image(frame, "image", ChannelType.JPEG, timestamp, metadata)
        client.send_data({"message": "message text"}, "event_name")
        client.send_data({"message": "message text"}, "event_name", ChannelType.JSON_LZ4)

How to create `callbacks_info`? E.g.:

        {
            "results": CallbackInfoClient(ChannelType.JSON, results_callback),
            "image": CallbackInfoClient(ChannelType.H264, image_callback, error_callback)
        }

Callbacks have data parameter: e.g. `def image_callback(data: Dict[str, Any]):`.
Image data dict including decoded frame (`data["frame"]`) and send timestamp (`data["timestamp"]`).

## Contributing, development

- The package is developed and tested with Python 3.8.
- Any contribution should go through a pull request from your fork.
- We use Pants to manage the code ([how to install it](https://www.pantsbuild.org/docs/installation)).
- Before committing, please run locally:
  - `pants fmt ::` - format all code according to our standard.
  - `pants lint ::` - checks formatting and few more things.
  - `pants check ::` - runs type checking (mypy).
  - `pants test ::` - runs Pytest tests.
- The same checks will be run within CI.
- A virtual environment with all necessary dependencies can be generated using `pants export ::`. 
  You may then activate the environment and add `era_5g_client` to your `PYTHONPATH`, which is equivalent 
  to installing a package using `pip install -e`.
- To generate distribution packages (`tar.gz` and `whl`), you may run `pants package ::`.
- For commit messages, please stick to 
[https://www.conventionalcommits.org/en/v1.0.0/](https://www.conventionalcommits.org/en/v1.0.0/).
