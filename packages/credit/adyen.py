import Adyen as AdyenCts
from packages.credit.acquirer import Acquirer, AcquirerResponse
from packages.common.cryptography import Cryptography
from packages.common.constants import (
    DEVELOPMENT_ENVIRONMENTS,
    APP_ENV,
    CAPTURE_METHOD_SYNCHRONOUS,
)
from packages.common.custom_exceptions import HttpException
from packages.common.errors import SysError
from http import HTTPStatus
import json


class Adyen(Acquirer):

    # identifier of adyen on db
    def _get_identifier(self):
        return 2

    def __init__(self, credentials):

        #### DOC REFERENCE
        #### https://docs.adyen.com/api-explorer/#/Payment/v64/overview

        super(Adyen, self).__init__()

        credentials = credentials["credentials"]
        self.adyen = AdyenCts.Adyen()
        self.client = self.adyen.client
        cryptography = Cryptography()
        self.client.merchant_account = cryptography.decrypt(
            credentials["merchant_account"]
        )
        self.client.username = cryptography.decrypt(credentials["username"])
        self.client.password = cryptography.decrypt(credentials["password"])
        self.client.platform = "test" if APP_ENV in DEVELOPMENT_ENVIRONMENTS else "live"

        self.STATUS_AUTHORIZED = "Authorised"
        self.STATUS_CAPTURED = "[capture-received]"
        self.STATUS_CANCELED = "[cancelOrRefund-received]"
        # self.DAYS_TO_CANCEL = 360

    def get_days_to_expire_authorization(self):
        return 28

    def _authorize(self, transaction):
        payment_data = self.__create_payment_data(transaction)
        response = self.adyen.payment.authorise(payment_data)
        authorize_acquirer_response = self.__create_acquirer_response(
            response, [self.STATUS_AUTHORIZED]
        )

        if (
            authorize_acquirer_response.success
            and transaction["payment"]["capture"] == CAPTURE_METHOD_SYNCHRONOUS
        ):
            authorize_full_response = authorize_acquirer_response.full_response

            acquirer_response = self._capture(transaction, authorize_acquirer_response)
            capture_full_response = acquirer_response.full_response
            acquirer_response.full_response = authorize_full_response
            acquirer_response.full_response["capture_response"] = capture_full_response
        else:
            acquirer_response = authorize_acquirer_response

        return acquirer_response

    def _capture(self, transaction, authorize_response=None):
        capture_data = self.__create_capture_data(transaction, authorize_response)
        response = self.adyen.payment.capture(capture_data)

        return self.__create_acquirer_response(response, [self.STATUS_CAPTURED])

    def _cancel(self, transaction):

        # Adyen dont have a defined max amount of days to cancel
        # if not transaction.can_cancel(self.DAYS_TO_CANCEL): [...]

        cancel_data = self.__create_cancel_data(transaction)
        response = self.adyen.payment.cancel_or_refund(cancel_data)
        return self.__create_acquirer_response(response, [self.STATUS_CANCELED])

    def _create_card_token(self, transaction):
        request = self.__create_card_token_data(transaction)
        response_create_token_adyen = self.adyen.payment.authorise(request)

        acquirer_response = self.__create_acquirer_response(
            response_create_token_adyen, [self.STATUS_AUTHORIZED]
        )

        if not acquirer_response.success:
            return (None, acquirer_response)

        try:
            token = acquirer_response.full_response["additionalData"][
                "recurring.recurringDetailReference"
            ]
        except Exception as e:
            token = None

        return (token, acquirer_response)

    def __create_card_token_data(self, transaction):
        t_credit_card = transaction["creditCard"]
        request = {
            "merchantAccount": self.client.merchant_account,
            "reference": transaction["transaction_id"],
            "amount": {
                "value": 0,
                "currency": "BRL",
            },
            "card": {
                "number": t_credit_card["number"],
                "expiryMonth": t_credit_card["expiryMonth"],
                "expiryYear": t_credit_card["expiryYear"],
                "cvc": t_credit_card["securityCode"],
                "holderName": t_credit_card["holderName"],
            },
            "shopperInteraction": "ContAuth",
            "recurring": {"contract": "RECURRING"},
            "recurringProcessingModel": "CardOnFile",
        }

        if (
            "customer" not in transaction
            or "documentNumber" not in transaction["customer"]
        ):
            raise Exception(
                "card owner document not found. To generate card token on Adyen the document is required."
            )
        request["shopperReference"] = transaction["customer"]["documentNumber"]

        if "customer" in transaction:
            if "email" in transaction["customer"]:
                request["shopperEmail"] = transaction["customer"]["email"]
            if "name" in transaction["customer"]:
                request["shopperName"] = transaction["customer"]["name"]

        return request

    def _consult(self, transaction):
        pass

    def __create_payment_data(self, transaction):
        request = {}
        request["merchantAccount"] = self.client.merchant_account
        request["reference"] = transaction["transaction_id"]

        installments = 1
        if "installments" in transaction["payment"]:
            installments = transaction["payment"]["installments"]

        request["installments"] = {"value": installments}
        request["amount"] = {
            "value": transaction["payment"]["amount"],
            "currency": transaction["payment"]["currency"],
        }

        if "token" in transaction["creditCard"]:
            request["recurring"] = {"contract": "RECURRING"}
            request["shopperInteraction"] = "ContAuth"
            request["selectedRecurringDetailReference"] = transaction["creditCard"][
                "token"
            ]
            if (
                "customer" in transaction
                and "documentNumber" in transaction["customer"]
            ):
                request["shopperReference"] = transaction["customer"]["documentNumber"]
        else:
            request["card"] = {
                "number": transaction["creditCard"]["number"],
                "expiryMonth": transaction["creditCard"]["expiryMonth"],
                "expiryYear": transaction["creditCard"]["expiryYear"],
                "cvc": transaction["creditCard"]["securityCode"],
                "holderName": transaction["creditCard"]["holderName"],
            }

        if "customer" in transaction:
            if "email" in transaction["customer"]:
                request["shopperEmail"] = transaction["customer"]["email"]
            if "name" in transaction["customer"]:
                request["shopperName"] = transaction["customer"]["name"]

            if "address" in transaction["customer"]:
                request["billingAddress"] = {
                    "city": transaction["customer"]["address"]["city"],
                    "street": transaction["customer"]["address"]["street"],
                    "country": transaction["customer"]["address"]["country"],
                    "houseNumberOrName": transaction["customer"]["address"]["number"],
                    "postalCode": transaction["customer"]["address"]["zipCode"],
                }
                if "state" in transaction["customer"]["address"]:
                    request["billingAddress"]["stateOrProvince"] = transaction[
                        "customer"
                    ]["address"]["state"]

        if "shipping" in transaction:
            request["deliveryAddress"] = {
                "city": transaction["shipping"]["city"],
                "street": transaction["shipping"]["street"],
                "country": transaction["shipping"]["country"],
                "houseNumberOrName": transaction["shipping"]["number"],
                "postalCode": transaction["shipping"]["zipCode"],
            }
            if "state" in transaction["shipping"]:
                request["deliveryAddress"]["stateOrProvince"] = transaction["shipping"][
                    "state"
                ]

        request["additionalData"] = {}
        if "subSeller" in transaction:
            t_sub_seller = transaction["subSeller"]
            request["additionalData"]["subMerchant.numberOfSubSellers"] = 1
            request["additionalData"]["subMerchant.subSeller1.id"] = t_sub_seller["id"]
            request["additionalData"]["subMerchant.subSeller1.name"] = t_sub_seller[
                "name"
            ][:22]
            request["additionalData"]["subMerchant.subSeller1.taxId"] = t_sub_seller[
                "documentNumber"
            ]
            request["additionalData"][
                "subMerchant.subSeller1.street"
            ] = "{}, {}".format(
                t_sub_seller["address"]["street"], t_sub_seller["address"]["number"]
            )[
                :60
            ]
            request["additionalData"]["subMerchant.subSeller1.city"] = t_sub_seller[
                "address"
            ]["city"][:13]
            request["additionalData"]["subMerchant.subSeller1.state"] = t_sub_seller[
                "address"
            ]["state"]
            request["additionalData"]["subMerchant.subSeller1.country"] = "BRA"
            request["additionalData"]["subMerchant.subSeller1.postalCode"] = "".join(
                filter(str.isdigit, t_sub_seller["address"]["zipCode"])
            )
            request["additionalData"]["subMerchant.subSeller1.mcc"] = transaction[
                "credentialAcquirer"
            ]["mcc"]
        return request

    def __create_acquirer_response(
        self, full_acquirer_response, successes_status, retry=False
    ):
        success = (
            True
            if full_acquirer_response.status_code == HTTPStatus.OK
            and hasattr(full_acquirer_response, "message")
            and (
                (
                    "resultCode" in full_acquirer_response.message
                    and full_acquirer_response.message["resultCode"] in successes_status
                )
                or (
                    "response" in full_acquirer_response.message
                    and full_acquirer_response.message["response"] in successes_status
                )
            )
            else False
        )

        if hasattr(full_acquirer_response, "raw_response"):
            full_acquirer_response = json.loads(full_acquirer_response.raw_response)
        else:
            full_acquirer_response = full_acquirer_response.__dict__

        response_code = full_acquirer_response.get("resultCode")
        message = ""
        pending = False

        if "pspReference" in full_acquirer_response:
            full_acquirer_response["PaymentId"] = full_acquirer_response["pspReference"]

        if "refusalReason" in full_acquirer_response:
            response_code = full_acquirer_response["refusalReason"]
            message = full_acquirer_response["refusalReason"]

        return AcquirerResponse(
            response_code, full_acquirer_response, message, success, pending
        )

    def __create_capture_data(self, transaction, authorize_response=None):
        request = {}
        request["merchantAccount"] = self.client.merchant_account

        if authorize_response:
            request["reference"] = transaction["transaction_id"]
            request["originalReference"] = authorize_response.full_response["PaymentId"]
            request["modificationAmount"] = {
                "value": transaction["payment"]["amount"],
                "currency": transaction["payment"]["currency"],
            }
        else:
            request["reference"] = transaction.get_transaction_id()
            request["originalReference"] = transaction.get_payment_id()
            request["modificationAmount"] = {
                "value": str(transaction.get_amount()),
                "currency": transaction.get_currency(),
            }

        return request

    def __create_cancel_data(self, transaction):
        request = {}
        request["merchantAccount"] = self.client.merchant_account
        request["reference"] = transaction.get_transaction_id()
        request["originalReference"] = transaction.get_payment_id()
        return request
