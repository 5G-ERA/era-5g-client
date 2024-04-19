import uuid
from typing import Tuple

from flask import Flask, Response, jsonify

app = Flask(__name__)


url = "http://localhost:5800"
counter = 1


@app.route("/Login", methods=["POST"])
def login() -> Tuple[Response, int]:
    # Generate a random token
    token = str(uuid.uuid4())
    return jsonify({"token": token}), 200


@app.route("/Task/Plan", methods=["POST"])
def create_task_plan() -> Response:
    global counter
    counter = 1
    action_plan_id = str(uuid.uuid4())
    response = {"ActionPlanId": action_plan_id}
    return jsonify(response)


@app.route("/orchestrate/orchestrate/plan/<string:action_plan_id>", methods=["GET"])
def get_orchestrated_plan(action_plan_id: str) -> Response:
    global counter
    url_local = url
    counter += 1
    if counter >= 10:
        url_local = "http://localhost:5801"
    response = {"actionSequence": [{"Services": [{"serviceStatus": "Active", "serviceUrl": url_local}]}]}
    return jsonify(response)


@app.route("/orchestrate/orchestrate/plan/<string:action_plan_id>", methods=["DELETE"])
def delete_orchestrated_plan(action_plan_id: str) -> Response:
    global counter
    counter = 1
    return jsonify({})


if __name__ == "__main__":
    app.run(debug=True)
