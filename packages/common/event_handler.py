import boto3
import json
import time
import copy
import sys
from datetime import datetime
from packages.common.storage import Storage
from boto3.dynamodb.conditions import Key
from packages.common.constants import (
    AWS_REGION,
    AWS_EVENT_BUS_NAME,
    REDIS_EXPIRATION_TIME_SECONDS,
    DEVELOPMENT_ENVIRONMENTS,
    APP_ENV,
)
from packages.common.general import obfuscate_creditcard, datetime_handler
from packages.common.errors import SysError, NotifyError
from packages.common.custom_exceptions import HttpException


class EventHandler:

    # event constants
    NEW_TRANSACTION_EVENT = "newTransactionEvent"
    NEW_CAPTURE_TRANSACTION_EVENT = "newCaptureTransactionEvent"
    NEW_CANCEL_TRANSACTION_EVENT = "newCancelTransactionEvent"
    NEW_CARD_TOKEN_EVENT = "newCardTokenEvent"
    VALID_TRANSACTION_EVENT = "validTransactionEvent"
    INVALID_TRANSACTION_EVENT = "invalidTransactionEvent"
    NOT_AUTHORIZED_TRANSACTION_EVENT = "notAuthorizedTransactionEvent"
    NOT_CANCELED_TRANSACTION_EVENT = "notCanceledTransactionEvent"
    NOT_CAPTURED_TRANSACTION_EVENT = "notCapturedTransactionEvent"
    CANNOT_CAPTURE_TRANSACTION_EVENT = "cannotCaptureTransactionEvent"
    NOT_GENERATED_CARD_TOKEN_EVENT = "notGeneratedCardTokenEvent"
    AUTHORIZED_TRANSACTION_EVENT = "authorizedTransactionEvent"
    CAPTURED_TRANSACTION_EVENT = "capturedTransactionEvent"
    CANCELED_TRANSACTION_EVENT = "canceledTransactionEvent"
    GENERATED_CARD_TOKEN_EVENT = "generatedCardTokenEvent"
    REQUEST_ASYNCHRONOUS_CAPTURE_EVENT = "requestAsynchronousCaptureEvent"
    PENDING_TRANSACTION_EVENT = "pendingTransactionEvent"

    # include in this list all events that are final (events that end the execution of the service)
    FINAL_EVENTS = [
        INVALID_TRANSACTION_EVENT,
        AUTHORIZED_TRANSACTION_EVENT,
        NOT_AUTHORIZED_TRANSACTION_EVENT,
        REQUEST_ASYNCHRONOUS_CAPTURE_EVENT,
        CAPTURED_TRANSACTION_EVENT,
        NOT_CAPTURED_TRANSACTION_EVENT,
        CANCELED_TRANSACTION_EVENT,
        NOT_CANCELED_TRANSACTION_EVENT,
        PENDING_TRANSACTION_EVENT,
    ]

    def __init__(self):
        self.events = []
        self.event_bus = boto3.client("events", region_name=AWS_REGION)
        self.ALL_EVENTS = [
            m
            for v, m in vars(EventHandler).items()
            if not (v.startswith("_") or callable(m))
        ]

        from packages.common.redis_cts import redis_cts

        self.redis = redis_cts

    def register(self, transaction_id, event_type, event_data={}):

        if event_type not in self.ALL_EVENTS:
            raise HttpException(
                *SysError.error_while_registering_event("Unknown event."),
                transaction_id=transaction_id
            )

        event_data_send = copy.deepcopy(event_data)
        event_data_send["transaction_id"] = transaction_id
        event_data_send["unixtimestamp"] = time.time()

        if "creditCard" in event_data_send:
            event_data_send["creditCard"] = obfuscate_creditcard(
                event_data_send["creditCard"]
            )

        event_json = {
            "transaction_id": transaction_id,
            "event_data": json.dumps(event_data_send),
            "event_type": event_type,
            "unixtimestamp": datetime.fromtimestamp(
                event_data_send["unixtimestamp"]
            ).isoformat(),
        }

        self.events.append(json.dumps(event_json))

        failed = False
        try:
            response = self.event_bus.put_events(
                Entries=[
                    {
                        "Source": "cts",
                        "Resources": [],
                        "DetailType": event_type,
                        "Detail": json.dumps(event_data_send),
                        "EventBusName": AWS_EVENT_BUS_NAME,
                    },
                ]
            )
        except Exception as e:
            failed = e

        if response["FailedEntryCount"] > 0 or failed:
            error_message = response if not failed else str(failed)

            if event_type == self.CAPTURED_TRANSACTION_EVENT:
                NotifyError.notify_by_email(
                    "Falha CTS - Cancelar transação {}".format(transaction_id),
                    {
                        "message": "A transação {} foi capturada com sucesso. Porém, houve uma falha ao salvar o evento e o usuário final receberá mensagem de erro. Favor estornar a transação na adquirente.".format(
                            transaction_id
                        ),
                        "error": error_message,
                    },
                )

            raise HttpException(
                *SysError.error_while_registering_event(),
                errors=error_message,
                transaction_id=transaction_id
            )

        try:

            if self.redis and event_type in self.FINAL_EVENTS:

                with self.redis.connection.pipeline() as pipe:

                    for event in self.events:
                        pipe.lpush(transaction_id, event)

                    acquirer_name, payment_id = self.get_acquirer_info_from_events()
                    if acquirer_name and payment_id:
                        payment_id_redis_key = "{}-{}".format(acquirer_name, payment_id)
                        pipe.mset({payment_id_redis_key: transaction_id})
                        pipe.expire(payment_id_redis_key, REDIS_EXPIRATION_TIME_SECONDS)

                    pipe.expire(transaction_id, REDIS_EXPIRATION_TIME_SECONDS)
                    
                    pipe.execute()

        except Exception as e:
            pass

        return True

    def fetch(self, transaction_id):

        from packages.common.database import Database

        if self.redis and self.redis.connection.exists(transaction_id):
            events = self.redis.connection.lrange(transaction_id, 0, -1)

            for idx, val in enumerate(events):
                events[idx] = json.loads(val)
                events[idx]["event_data"] = json.loads(events[idx]["event_data"])
                events[idx]["unixtimestamp"] = datetime.fromisoformat(
                    events[idx]["unixtimestamp"]
                )

            return events

        db = Database()
        response = db.select(
            "transaction_event.*",
            "transaction_event",
            where={"transaction_event.transaction_id": transaction_id,},
        )

        if self.redis:
            with self.redis.connection.pipeline() as pipe:

                for idx, val in enumerate(response):
                    pipe.lpush(
                        transaction_id, json.dumps(val, default=datetime_handler)
                    )
                    response[idx]["event_data"] = json.loads(val["event_data"])

                if response:
                    pipe.expire(transaction_id, REDIS_EXPIRATION_TIME_SECONDS)

                pipe.execute()
        else:
            for idx, val in enumerate(response):
                response[idx]["event_data"] = json.loads(val["event_data"])

        return response

    def get_acquirer_info_from_events(self):
        acquirer_name = payment_id = None

        if "provider" in self.events[0]:
            try:
                event_tmp = json.loads(self.events[0])
                event_data_tmp = json.loads(event_tmp["event_data"])
                acquirer_name = event_data_tmp["provider"]
            except Exception as e:
                Storage.store_exception(e)

        if "PaymentId" in self.events[-1]:
            try:
                event_tmp = json.loads(self.events[-1])
                event_data_tmp = json.loads(event_tmp["event_data"])
                payment_id = event_data_tmp["PaymentId"]
            except Exception as e:
                Storage.store_exception(e)

        return acquirer_name, payment_id
