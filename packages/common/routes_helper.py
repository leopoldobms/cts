from flask import request
from http import HTTPStatus
import json
from packages.common.errors import SysError
from packages.common.custom_exceptions import HttpException
from packages.common.transaction import Transaction
from packages.common.general import dict_raise_on_duplicates
from packages.common.storage import Storage
from packages.credit.schemas.credentials_schema import CredentialAcquirerSchema


class Routes:
    @staticmethod
    def dynamic_method(params, request_data):
        status_code, response = "", ""

        try:

            service, action, extra = params.split("/")

            transaction, credentials = Routes.get_transaction_and_credentials(
                action, extra, request_data
            )

            if not credentials:
                raise ValueError("credentialAcquirer not found on request data")

            if action in ["authorize", "create_card_token", "recive_pending_payments"]:
                provider = extra
            else:
                provider = transaction.get_provider()

            module = __import__(f"packages.{service}.{provider}", fromlist=[None])
            class_ = getattr(module, provider.capitalize())
            instance = class_(credentials)
            method = getattr(instance, action)

            return (method, transaction)

        except ValueError as error:

            message, code, http_code = SysError.missing_parameter()

            if str(error) == "not enough values to unpack (expected 3, got 1)":
                response = "Missing action parameter."

            elif str(error) == "not enough values to unpack (expected 3, got 2)":
                response = "Missing extra parameter."

            elif str(error) == "credentialAcquirer not found on request data":
                response = "Missing credentials."
            else:
                response = str(error)

        except ModuleNotFoundError as error:

            message, code, http_code = SysError.module_not_found()

            response = str(error).replace("packages.", "")

        except AttributeError as error:

            message, code, http_code = SysError.action_not_found()

            response = str(error)

        raise HttpException(message, code, http_code, response)

    @staticmethod
    def get_transaction_and_credentials(action, acquirer_name, request_data):
        transaction = credentials = None

        if action not in ["authorize", "create_card_token", "recive_pending_payments"]:
            transaction = Transaction(acquirer_name)

        if action == "recive_pending_payments":
            transaction_id = Routes.get_transaction_id_from_request_data(
                acquirer_name, request_data
            )
            transaction = Transaction(transaction_id)

        if transaction:
            credentials = transaction.get_credentials()

        if not credentials and type(request_data.get("credentialAcquirer")) == dict:
            credentials = CredentialAcquirerSchema().load(
                request_data["credentialAcquirer"]
            )

        return transaction, credentials

    @staticmethod
    def validate_request_data():
        request_data = request.get_data(as_text=True)
        try:
            request_data = json.loads(
                request_data, object_pairs_hook=dict_raise_on_duplicates
            )
        except ValueError as e:
            if request.mimetype == "application/x-www-form-urlencoded":
                request_data = request.form.to_dict()
            else:
                request_data = {"invalid_request_data": request.get_data(as_text=True)}

        return request_data

    @staticmethod
    def get_transaction_id_from_request_data(acquirer_name, request_data):
        transaction_id = None

        if acquirer_name == "mercadopago":
            payment_id = request_data["data"]["id"]
            transaction_id = Transaction.get_transaction_id_from_payment_id(
                payment_id, acquirer_name
            )

        elif acquirer_name == "payu":
            transaction_id = request.form["reference_sale"]

        else:
            raise ValueError(
                "acquirer {} not implemented on get_transaction_id_from_request_data".format(
                    acquirer_name
                )
            )

        return transaction_id
