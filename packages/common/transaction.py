from http import HTTPStatus
from packages.common.errors import SysError
from packages.common.event_handler import EventHandler
from packages.common.general import diff_current_date
from packages.common.custom_exceptions import HttpException
from packages.common.constants import (
    TIMES_TRANSACTION_RETRY,
    SECONDS_INTERVAL_TRANSACTION_RETRY,
)
from packages.common.storage import Storage
import uuid
import time


class Transaction:
    def __init__(self, transaction_id):

        self.event_handler = EventHandler()

        self.transaction = self.event_handler.fetch(transaction_id)

        if not self.transaction or not self.__has_final_event(self.transaction):
            for i in range(1, TIMES_TRANSACTION_RETRY + 1):
                time.sleep(i * SECONDS_INTERVAL_TRANSACTION_RETRY)
                self.transaction = self.event_handler.fetch(transaction_id)
                if self.transaction and self.__has_final_event(self.transaction):
                    break

            if not self.transaction or not self.__has_final_event(self.transaction):
                raise HttpException(
                    *SysError.transaction_not_found(), transaction_id=transaction_id
                )

        self.__authorized = False
        self.__refused = False
        self.__canceled = False
        self.__captured = False
        self.__pending = False

        self.__notification = None
        self.__reference = None
        self.__credentials = None

        for t in self.transaction:
            if t["event_type"] == EventHandler.PENDING_TRANSACTION_EVENT:
                self.__pending = True
                self.__payment_id = t["event_data"]["PaymentId"]
            elif t["event_type"] == EventHandler.AUTHORIZED_TRANSACTION_EVENT:
                self.__authorized = True
                self.__authorized_unix_timestamp = t["unixtimestamp"]

                if "PaymentId" in t["event_data"]:
                    self.__payment_id = t["event_data"]["PaymentId"]
            elif t["event_type"] == EventHandler.CAPTURED_TRANSACTION_EVENT:
                self.__capture_unix_timestamp = t["unixtimestamp"]
                self.__captured = True
            elif t["event_type"] == EventHandler.NOT_AUTHORIZED_TRANSACTION_EVENT:
                self.__refused = True
            elif t["event_type"] == EventHandler.CANCELED_TRANSACTION_EVENT:
                self.__canceled = True
            elif t["event_type"] == EventHandler.NEW_TRANSACTION_EVENT:
                self.__acquirer = t["event_data"]["provider"]
                self.__currency = t["event_data"]["payment"]["currency"]
                self.__amount = t["event_data"]["payment"]["amount"]
                self.__transaction_id = t["event_data"]["transaction_id"]
                self.__reference = t["event_data"]["reference"]
                self.__credentials = t["event_data"]["credentialAcquirer"]

                if "notification" in t["event_data"]:
                    self.__notification = {
                        "url": t["event_data"]["notification"]["url"],
                        "login": t["event_data"]["notification"]["login"],
                        "password": t["event_data"]["notification"]["password"],
                    }

            # REMOVER DEPOIS
            if "credentialAcquirer" in t["event_data"]:
                self.__credentials = t["event_data"]["credentialAcquirer"]

    def can_capture(self):
        return (
            (self.__pending or self.__authorized)
            and not self.__captured
            and not self.__canceled
        )

    def can_cancel(self, days=365):
        if self.__canceled or (not self.__authorized and not self.__pending):
            return False

        if (
            self.__authorized
            and diff_current_date(self.__authorized_unix_timestamp).days > days
        ):
            return False

        return True

    def authorization_expired(self, days):
        if (
            self.__authorized
            and diff_current_date(self.__authorized_unix_timestamp).days > days
        ):
            return True
        return False

    def get_amount(self):
        return self.__amount

    def get_currency(self):
        return self.__currency

    def get_payment_id(self):
        return self.__payment_id

    def get_provider(self):
        return self.__acquirer

    def get_transaction_id(self):
        return self.__transaction_id

    def get_reference(self):
        return self.__reference

    def get_notification_data(self):
        return self.__notification

    def get_credentials(self):
        return self.__credentials

    # is pending now?
    def is_pending(self):
        if (
            not (self.__pending)
            or self.__captured
            or self.__authorized
            or self.__refused
        ):
            return False
        return self.__pending

    def is_captured(self):
        return self.__captured

    def generate_transaction_id(prefix=""):
        return prefix + "-" + str(uuid.uuid4())

    def __has_final_event(self, transaction):

        events_list = [event["event_type"] for event in transaction]

        for transaction_final_event in EventHandler.FINAL_EVENTS:
            if transaction_final_event in events_list:
                return True

        return False

    def get_transaction_id_from_payment_id(payment_id, acquirer_name):
        from packages.common.database import Database
        from packages.common.redis_cts import redis_cts

        transaction_id = None

        redis_key = "{}-{}".format(acquirer_name, payment_id)
        if redis_cts:
            redis_data = redis_cts.connection.mget(redis_key)[0]
            transaction_id = redis_data.decode("utf-8") if redis_data else None

        if not transaction_id:
            try:
                db = Database()
                transaction_id_response = db.select(
                    "tp.transaction_id",
                    "transactionid_paymentid tp",
                    ["JOIN acquirer aq ON (tp.acquirer_id = aq.id)"],
                    {
                        "tp.payment_id": payment_id,
                        "aq.name": acquirer_name,
                    },
                )

                if transaction_id_response:
                    return transaction_id_response[0]["transaction_id"]
                else:
                    raise Exception(f"transaction not found. PaymentId: {payment_id}")

            except Exception as e:
                Storage.store_exception(e)
                raise e

        return transaction_id
