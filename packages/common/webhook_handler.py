import json
import hashlib
import boto3
from packages.common.constants import (
    AWS_WEBHOOK_QUEUE_NAME,
    AWS_REGION,
)


class WebhookHandler:

    TYPE_PAYMENT = "payment"
    TYPE_SIGNATURE = "signature"

    ACTION_UPDATED = "updated"

    PAYMENT_STATUS_AUTHORIZED = "authorized"
    PAYMENT_STATUS_CAPTURED = "captured"
    PAYMENT_STATUS_NOT_AUTHORIZED = "notAuthorized"

    def __init__(self):
        sqs = boto3.resource("sqs", region_name=AWS_REGION)
        self.queue_name = AWS_WEBHOOK_QUEUE_NAME
        self.webhook_queue = sqs.get_queue_by_name(QueueName=self.queue_name)

    def send(self, msg):
        if not isinstance(msg, WebhookMessage):
            raise Exception("Argument msg should be instance of WebhookMessage")

        msg_json = msg.to_json()
        response = self.webhook_queue.send_message(MessageBody=msg_json)
        if not self.msg_sent_sucessfully(msg_json, response):
            raise Exception(
                "Error trying to send msg: {} to queue {}".format(msg, self.queue_name)
            )

    def msg_sent_sucessfully(self, msg, response):
        return (
            response.get("MD5OfMessageBody")
            == hashlib.md5(msg.encode("utf-8")).hexdigest()
        )


class WebhookMessage:
    def __init__(self, msg_type, action, url, login, password, message):
        self.msg = {
            "url": url,
            "login": login,
            "password": password,
            "type": msg_type,
            "action": action,
            "message": message,
        }

    def to_json(self):
        return json.dumps(self.msg)
