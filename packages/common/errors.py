from http import HTTPStatus
from packages.common.constants import AWS_REGION, AWS_SNS_ALERT_TOPIC, AWS_ACCOUNT_ID
import boto3
import json


class SysError:

    PREFIX = "SYS"

    def validation_error():
        code = SysError.PREFIX + "1"
        message = "Validation Error."
        http_status = HTTPStatus.UNPROCESSABLE_ENTITY
        return message, code, http_status

    def cannot_capture():
        code = SysError.PREFIX + "2"
        message = "Cannot capture."
        http_status = HTTPStatus.UNPROCESSABLE_ENTITY
        return message, code, http_status

    def cannot_cancel():
        code = SysError.PREFIX + "3"
        message = "Cannot cancel."
        http_status = HTTPStatus.UNPROCESSABLE_ENTITY
        return message, code, http_status

    def error_while_consulting():
        code = SysError.PREFIX + "4"
        message = "Error while consulting transaction."
        http_status = HTTPStatus.INTERNAL_SERVER_ERROR
        return message, code, http_status

    def error_while_registering_event(why=""):
        code = SysError.PREFIX + "5"
        message = "Error while registering event. {}".format(why)
        http_status = HTTPStatus.INTERNAL_SERVER_ERROR
        return message, code, http_status

    def missing_parameter():
        code = SysError.PREFIX + "6"
        message = "Missing parameter."
        http_status = HTTPStatus.BAD_REQUEST
        return message, code, http_status

    def module_not_found():
        code = SysError.PREFIX + "7"
        message = "Module not found, service or provider are wrong."
        http_status = HTTPStatus.BAD_REQUEST
        return message, code, http_status

    def action_not_found():
        code = SysError.PREFIX + "8"
        message = "Action not found."
        http_status = HTTPStatus.BAD_REQUEST
        return message, code, http_status

    def transaction_not_found():
        code = SysError.PREFIX + "9"
        message = "This transaction does not exists."
        http_status = HTTPStatus.NOT_FOUND
        return message, code, http_status

    def database_comunication_error():
        code = SysError.PREFIX + "10"
        message = "Error establishing a database connection."
        http_status = HTTPStatus.INTERNAL_SERVER_ERROR
        return message, code, http_status

    def acquirer_service_unavailable():
        code = SysError.PREFIX + "11"
        message = "Acquirer service unavailable."
        http_status = HTTPStatus.INTERNAL_SERVER_ERROR
        return message, code, http_status

    def cannot_generate_card_token():
        code = SysError.PREFIX + "12"
        message = "Error while generating card token. Please, verify the card info."
        http_status = HTTPStatus.UNPROCESSABLE_ENTITY
        return message, code, http_status

    def duplicated_keys_json_request():
        code = SysError.PREFIX + "13"
        message = "Your request have duplicated keys."
        http_status = HTTPStatus.BAD_REQUEST
        return message, code, http_status

    def transaction_is_not_pending():
        code = SysError.PREFIX + "14"
        message = "Transaction is not pending."
        http_status = HTTPStatus.OK
        return message, code, http_status

    def webhook_update_error():
        code = SysError.PREFIX + "15"
        message = "Error updating transaction from webhook."
        http_status = HTTPStatus.BAD_REQUEST
        return message, code, http_status

    def could_not_capture():
        code = SysError.PREFIX + "16"
        message = "Error trying to capture. Please try again."
        http_status = HTTPStatus.UNPROCESSABLE_ENTITY
        return message, code, http_status

    def authorization_expired():
        code = SysError.PREFIX + "17"
        message = "The authorization is expired."
        http_status = HTTPStatus.BAD_REQUEST
        return message, code, http_status

class NotifyError:
    def notify_by_email(subject, message):
        client = boto3.client("sns", region_name=AWS_REGION)
        topic_arn = "arn:aws:sns:{}:{}:{}".format(
            AWS_REGION, AWS_ACCOUNT_ID, AWS_SNS_ALERT_TOPIC
        )

        client.publish(TopicArn=topic_arn, Message=json.dumps(message), Subject=subject)

        return True
