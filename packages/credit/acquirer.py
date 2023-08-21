from packages.credit.acquirers_interface import AcquirersInterface
from packages.credit.schemas.authorization_schema import (
    CreditAuthorizationSchema,
    CreditAuthorizationWithTokenSchema,
)
from packages.credit.schemas.card_token_schema import CreditCardTokenSchema
from marshmallow import ValidationError
from http import HTTPStatus
from packages.common.custom_exceptions import HttpException
from packages.common.secret_manager import secret_manager
from packages.common.database import Database
from packages.common.errors import SysError
from packages.common.storage import Storage
from packages.common.event_handler import EventHandler
from packages.common.transaction import Transaction
from packages.common.constants import (
    DEFAULT_ERROR_MESSAGE_CODE,
    DEFAULT_SUCCESS_MESSAGE_CODE,
    CAPTURE_METHOD_SYNCHRONOUS,
)
import inspect
import sys
from packages.common.webhook_handler import WebhookHandler, WebhookMessage
import copy


class Acquirer(AcquirersInterface):
    """docstring for ClassName"""

    def __init__(self):
        self.event_handler = EventHandler()
        self.provider = self.__class__.__name__.lower()

    def authorize(self, request_data, transaction=None):

        acquirer_credential_id = str(
            request_data["credentialAcquirer"]["acquirerCredentialId"]
        )
        transaction_id = Transaction.generate_transaction_id(acquirer_credential_id)
        request_data["transaction_id"] = transaction_id
        request_data["provider"] = self.provider
        self.event_handler.register(
            transaction_id, EventHandler.NEW_TRANSACTION_EVENT, request_data
        )
        del request_data["provider"]

        # validate transaction
        try:
            if "creditCard" in request_data and "token" in request_data["creditCard"]:
                credit_authorization_schema = CreditAuthorizationWithTokenSchema()
            else:
                credit_authorization_schema = CreditAuthorizationSchema()

            transaction = credit_authorization_schema.load(request_data)

        except ValidationError as e:
            raise HttpException(
                *SysError.validation_error(),
                errors=e.messages["errors"],
                transaction_id=transaction_id,
                event_handler=self.event_handler,
                error_event=EventHandler.INVALID_TRANSACTION_EVENT,
                event_data=e.messages,
            )

        self.event_handler.register(
            transaction_id, EventHandler.VALID_TRANSACTION_EVENT
        )

        # authorize transaction
        try:
            if "creditCard" in transaction and "token" in transaction["creditCard"]:
                transaction["cardToken"] = transaction["creditCard"]["token"]
                transaction["creditCard"]["token"] = "-".join(
                    transaction["creditCard"]["token"].split("-")[1:]
                )
            acquirer_response = self._authorize(transaction)
            cts_response = self.__get_cts_response(
                acquirer_response,
                acquirer_response.full_response.get("payment_method_id"),
            )

        except Exception as e:
            acquirer_response, cts_response = self.__handleAcquirerResponseException(e)

        acquirer_response_gateway = copy.deepcopy(acquirer_response.full_response)
        acquirer_info = {
            "payment_id": acquirer_response_gateway.pop("PaymentId", None),
            "response": acquirer_response_gateway,
        }

        acquirer_response.full_response["provider"] = self.provider

        if cts_response["http_status"] != HTTPStatus.OK or acquirer_response.pending:
            if acquirer_response.pending:
                error_event = EventHandler.PENDING_TRANSACTION_EVENT
                acquirer_response.full_response["credentialAcquirer"] = request_data[
                    "credentialAcquirer"
                ]

            else:
                error_event = EventHandler.NOT_AUTHORIZED_TRANSACTION_EVENT

            raise HttpException(
                cts_response["message"],
                cts_response["code"],
                cts_response["http_status"],
                transaction_id=transaction_id,
                event_handler=self.event_handler,
                error_event=error_event,
                event_data=acquirer_response.full_response,
                acquirer_info=acquirer_info,
            )

        self.event_handler.register(
            transaction_id,
            EventHandler.AUTHORIZED_TRANSACTION_EVENT,
            acquirer_response.full_response,
        )

        # captured?
        capture_method = transaction["payment"]["capture"]
        if capture_method != "NO":
            capture_event = (
                EventHandler.CAPTURED_TRANSACTION_EVENT
                if capture_method == CAPTURE_METHOD_SYNCHRONOUS
                else EventHandler.REQUEST_ASYNCHRONOUS_CAPTURE_EVENT
            )

            capture_data = {}
            if type(
                acquirer_response.full_response
            ) == dict and acquirer_response.full_response.get("capture_response"):
                capture_data = acquirer_response.full_response["capture_response"]
            self.event_handler.register(transaction_id, capture_event, capture_data)

        return (
            {
                "code": cts_response["code"],
                "message": cts_response["message"],
                "transaction_id": transaction_id,
                "antifraud": acquirer_response.antifraud,
                "acquirer_info": acquirer_info,
            },
            HTTPStatus.OK,
        )

    def cancel(self, request_data, transaction):

        if not transaction.can_cancel():
            raise HttpException(
                *SysError.cannot_cancel(),
                transaction_id=transaction.get_transaction_id(),
            )

        self.event_handler.register(
            transaction.get_transaction_id(), EventHandler.NEW_CANCEL_TRANSACTION_EVENT
        )
        event = EventHandler.CANCELED_TRANSACTION_EVENT

        try:
            acquirer_response = self._cancel(transaction)
            cts_response = self.__get_cts_response(acquirer_response)
        except Exception as e:
            acquirer_response, cts_response = self.__handleAcquirerResponseException(e)

        if cts_response["http_status"] != HTTPStatus.OK:
            event = EventHandler.NOT_CANCELED_TRANSACTION_EVENT

        self.event_handler.register(
            transaction.get_transaction_id(),
            event,
            acquirer_response.full_response,
        )

        if event == EventHandler.NOT_CANCELED_TRANSACTION_EVENT:
            raise HttpException(
                cts_response["message"],
                cts_response["code"],
                cts_response["http_status"],
                transaction_id=transaction.get_transaction_id(),
            )

        return (
            {
                "code": cts_response["code"],
                "message": cts_response["message"],
                "transaction_id": transaction.get_transaction_id(),
            },
            HTTPStatus.OK,
        )

    def capture(self, request_data, transaction):

        self.event_handler.register(
            transaction.get_transaction_id(), EventHandler.NEW_CAPTURE_TRANSACTION_EVENT
        )

        if not transaction.can_capture():
            raise HttpException(
                *SysError.cannot_capture(),
                transaction_id=transaction.get_transaction_id(),
                event_handler=self.event_handler,
                error_event=EventHandler.CANNOT_CAPTURE_TRANSACTION_EVENT,
            )

        if transaction.authorization_expired(self.get_days_to_expire_authorization()):
            raise HttpException(
                *SysError.authorization_expired(),
                transaction_id=transaction.get_transaction_id(),
            )

        event = EventHandler.CAPTURED_TRANSACTION_EVENT

        try:
            acquirer_response = self._capture(transaction)
            cts_response = self.__get_cts_response(acquirer_response)
        except Exception as e:
            if isinstance(e, HttpException):
                raise e
            acquirer_response, cts_response = self.__handleAcquirerResponseException(e)

        if cts_response["http_status"] != HTTPStatus.OK:
            event = EventHandler.NOT_CAPTURED_TRANSACTION_EVENT

        self.event_handler.register(
            transaction.get_transaction_id(),
            event,
            acquirer_response.full_response,
        )

        if event == EventHandler.NOT_CAPTURED_TRANSACTION_EVENT:
            raise HttpException(
                cts_response["message"],
                cts_response["code"],
                cts_response["http_status"],
                transaction_id=transaction.get_transaction_id(),
            )

        return (
            {
                "code": cts_response["code"],
                "message": cts_response["message"],
                "transaction_id": transaction.get_transaction_id(),
            },
            HTTPStatus.OK,
        )

    def consult(self, request_data, transaction=None):
        try:
            acquirer_response = self._consult(transaction)
        except:
            raise HttpException(
                *SysError.error_while_consulting(),
                transaction_id=transaction.get_transaction_id(),
            )

        return acquirer_response, HTTPStatus.OK

    def recive_pending_payments(self, request_data, transaction=None):

        if not transaction.is_pending():

            return (
                {
                    "message": "Transaction is not pending SYS14!",
                    "transaction": str(transaction.__dict__),
                },
                HTTPStatus.OK,
            )

        (
            transaction,
            events_to_update,
            webhook_status,
            payment_info,
        ) = self._recive_pending_payments(request_data, transaction)

        sended_notification = False
        transaction_id = transaction.get_transaction_id()

        if events_to_update:
            try:
                if transaction.get_notification_data():
                    webhook_handler = WebhookHandler()
                    notification_data = transaction.get_notification_data()
                    webhook_msg = WebhookMessage(
                        WebhookHandler.TYPE_PAYMENT,
                        WebhookHandler.ACTION_UPDATED,
                        notification_data["url"],
                        notification_data["login"],
                        notification_data["password"],
                        {
                            "transaction_id": transaction_id,
                            "reference": transaction.get_reference(),
                            "status": webhook_status,
                        },
                    )
                    try:
                        webhook_handler.send(webhook_msg)
                        sended_notification = True
                    except Exception as e:
                        Storage.store_exception(e)
                        sended_notification = str(e)

                for event_to_update in events_to_update:
                    self.event_handler.register(
                        transaction_id, event_to_update, payment_info
                    )
            except Exception as e:
                raise e

        return (
            {
                "message": "Everything alright!",
                "payment_info": payment_info,
                "transaction_notification_data": transaction.get_notification_data(),
                "sended_notification": sended_notification,
                "transaction": str(transaction.__dict__),
                "events_to_update": str(events_to_update),
            },
            HTTPStatus.OK,
        )

    def create_card_token(self, request_data, transaction=None):
        acquirer_credential_id = str(
            request_data["credentialAcquirer"]["acquirerCredentialId"]
        )
        transaction_id = Transaction.generate_transaction_id(acquirer_credential_id)
        credit_card_token_schema = CreditCardTokenSchema()

        self.event_handler.register(
            transaction_id, EventHandler.NEW_CARD_TOKEN_EVENT, request_data
        )

        try:
            transaction = credit_card_token_schema.load(request_data)
            transaction["transaction_id"] = transaction_id

        except ValidationError as e:
            raise HttpException(
                *SysError.validation_error(),
                errors=e.messages["errors"],
                transaction_id=transaction_id,
                event_handler=self.event_handler,
                error_event=EventHandler.INVALID_TRANSACTION_EVENT,
                event_data=e.messages,
            )

        self.event_handler.register(
            transaction_id, EventHandler.VALID_TRANSACTION_EVENT
        )

        acquirer_response = None
        try:
            card_token, acquirer_response = self._create_card_token(transaction)
            if not card_token:
                raise Exception("Card token is null")
            card_token = "{}-{}".format(acquirer_credential_id, card_token)
        except Exception as e:
            event_data = (
                acquirer_response.full_response if acquirer_response else str(e)
            )
            raise HttpException(
                *SysError.cannot_generate_card_token(),
                transaction_id=transaction_id,
                error_event=EventHandler.NOT_GENERATED_CARD_TOKEN_EVENT,
                event_handler=self.event_handler,
                event_data={"error_message": event_data},
            )

        self.event_handler.register(
            transaction_id,
            EventHandler.GENERATED_CARD_TOKEN_EVENT,
            {
                "card_token": card_token,
                "provider": self.provider,
                "acquirer_response": acquirer_response.full_response,
            },
        )

        return (
            {
                "code": DEFAULT_SUCCESS_MESSAGE_CODE,
                "transaction_id": transaction_id,
                "card_token": card_token,
            },
            HTTPStatus.OK,
        )

    def __get_cts_response(self, acquirer_response, card_brand=""):

        # get the acquirer method who is looking for the response (authorize, capture, cancel..etc)
        acquirer_method = inspect.stack()[1].function

        if acquirer_response.success == True:
            return self.__get_default_message(
                success=True, acquirer_method=acquirer_method
            )

        if (
            acquirer_response.retry
            and not acquirer_response.success
            and acquirer_method == "capture"
        ):
            message, code, status = SysError.could_not_capture()
            return {"code": code, "message": message, "http_status": status}

        try:
            db = Database()
                query = "ar.brand is null OR ar.brand" # abecs e cielo only
            else:
                query = "ar.brand not null AND ar.brand" # abecs only

            cts_responses = db.select(
                "cts.code, cts.message, cts.http_status, ar.message as ar_message",
                "cts_response cts",
                ["JOIN acquirer_response ar on ar.cts_response_id = cts.id"],
                ["JOIN acquirer ac on ac.id = cts.id"],
                {
                    "ar.code": acquirer_response.response_code,
                    query: card_brand,
                    "ar.acquirer_id": self._get_identifier(),
                    "ar.active": 1,
                },
            )

            if cts_responses:
                return cts_responses[0]

            else:
                # none of them matches the acquirer message, so we save this unexpected message and return the default one
                db.insert(
                    {
                        "code": acquirer_response.response_code,
                        "message": acquirer_response.message,
                        "brand": card_brand,
                        "acquirer_id": self._get_identifier(),
                    },
                    "acquirer_unexpected_responses",
                )
                return self.__get_default_message(success=False)

        except Exception as e:
            Storage.store_exception(e)
            raise e

    def __handleAcquirerResponseException(self, exception):
        acquirer_response = AcquirerResponse(None, {"error_message": str(exception)})

        if "pymysql" in str(type(exception)) or "port" in str(exception):
            message, code, http_code = SysError.database_comunication_error()
        else:
            print(sys.exc_info())
            print(str(exception))
            message, code, http_code = SysError.acquirer_service_unavailable()

        cts_response = {
            "code": code,
            "message": message,
            "http_status": http_code,
        }
        return acquirer_response, cts_response

    def __get_default_message(self, success, acquirer_method=None):

        if success:
            cts_code = DEFAULT_SUCCESS_MESSAGE_CODE
        else:
            cts_code = DEFAULT_ERROR_MESSAGE_CODE

        try:
            db = Database()
            default_error_message = db.select(
                "cts.code, cts.message, cts.http_status",
                "cts_response cts",
                where={"cts.code": cts_code},
            )
            return default_error_message[0]

        except Exception as e:
            Storage.store_exception(e)
            raise e


class AcquirerResponse:
    def __init__(
        self,
        response_code,
        full_response={},
        message=None,
        success=None,
        pending=None,
        antifraud=False,
        **kwargs
    ):
        self.response_code = response_code
        self.full_response = full_response
        self.message = message
        self.success = success
        self.pending = pending
        self.antifraud = antifraud
        self.retry = kwargs.get("retry", False)
