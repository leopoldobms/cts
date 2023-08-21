import json
from http import HTTPStatus
from datetime import datetime
from packages.common.storage import Storage
from flask import jsonify, Blueprint, request
from packages.common.routes_helper import Routes
from packages.common.custom_exceptions import HttpException
from packages.common.general import dict_raise_on_duplicates
import packages.common.secret_manager as secret_manager
import packages.common.redis_cts as redis_file
from packages.common.event_handler import EventHandler

routes = Blueprint("routes", __name__)
secret_manager.init()


@routes.route("/v1/<path:params>", methods=["POST"])
def handler(params):
    redis_file.init()
    request_data = Routes.validate_request_data()
    method, transaction = Routes.dynamic_method(params, request_data)
    response, status_code = method(request_data, transaction)

    return jsonify(response), status_code


@routes.errorhandler(Exception)
def handle_error(e):

    response = Storage.store_exception(e)
    response["errors"] = str(e)

    return jsonify(response), 500


@routes.errorhandler(HttpException)
def http_handle_error(e):
    if e.transaction_id and e.error_event and e.event_handler:
        e.event_handler.register(e.transaction_id, e.error_event, e.event_data)

    if e.http_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        response = {**Storage.store_exception(e), **e.response}
    else:
        response = e.response

    return jsonify(response), e.http_code
