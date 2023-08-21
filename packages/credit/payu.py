from packages.common.custom_exceptions import HttpException
from packages.credit.acquirer import Acquirer, AcquirerResponse
from packages.common.secret_manager import secret_manager
from packages.common.constants import (
    DEVELOPMENT_ENVIRONMENTS,
    APP_ENV,
    CAPTURE_METHOD_SYNCHRONOUS
)
from packages.credit.payusdk.payment import Payments
from packages.credit.payusdk.consult import Consult
from packages.common.errors import SysError
from packages.common.event_handler import EventHandler
from packages.common.general import mask_cpf_cnpj, truncate
from packages.common.transaction import Transaction
from packages.common.event_handler import EventHandler
from packages.common.webhook_handler import WebhookHandler, WebhookMessage
from packages.common.cryptography import Cryptography
from packages.common.storage import Storage
from http import HTTPStatus
from packages.common.errors import SysError


class Payu(Acquirer):

    # identifier of PayU on db
    def _get_identifier(self):
        return 4

    def __init__(self, credentials):
        super(Payu, self).__init__()
        credentials = credentials["credentials"]
        cryptography = Cryptography()
        sandbox = True if APP_ENV in DEVELOPMENT_ENVIRONMENTS else False

        self.payu = Payments(
            cryptography.decrypt(credentials["api_login"]),
            cryptography.decrypt(credentials["api_key"]),
            cryptography.decrypt(credentials["merchant_id"]),
            cryptography.decrypt(credentials["account_id"]),
            sandbox=sandbox,
        )

        self.consult = Consult(
            cryptography.decrypt(credentials["api_login"]),
            cryptography.decrypt(credentials["api_key"]),
            cryptography.decrypt(credentials["merchant_id"]),
            cryptography.decrypt(credentials["account_id"]),
            sandbox=sandbox,
        )

        self.DAYS_TO_CANCEL = 90
        self.STATUS_APPROVED = "APPROVED"
        self.STATUS_ERROR = "ERROR"
        self.STATUS_SUCCESS = "SUCCESS"
        self.STATUS_AUTHORIZED = "AUTHORIZED"
        self.STATUS_CAPTURED = "CAPTURED"
        self.STATUS_DECLINED = "DECLINED"

    def get_days_to_expire_authorization(self):
        return 7

    def _authorize(self, transaction):

        payment_data = self.__create_payment_data(transaction)
        acquirer_response = self.payu.authorize(payment_data)

        return self.__create_acquirer_response(
            acquirer_response, [self.STATUS_APPROVED]
        )

    def _cancel(self, transaction):
        if not transaction.can_cancel(self.DAYS_TO_CANCEL):
            raise HttpException(
                *SysError.cannot_cancel(),
                transaction_id=transaction.get_transaction_id(),
            )
        transaction_type = "REFUND" if transaction.is_captured() == True else "VOID"
        payment_data = self.__create_update_data(transaction, transaction_type)
        acquirer_response = self.payu.update_transaction(payment_data)
        return self.__create_acquirer_response(
            acquirer_response, [self.STATUS_APPROVED]
        )

    def _capture(self, transaction):
        payment_data = self.__create_update_data(transaction, "CAPTURE")
        acquirer_response = self.payu.update_transaction(payment_data)
        return self.__create_acquirer_response(
            acquirer_response, [self.STATUS_APPROVED]
        )

    def _consult(self, transaction):
        return {}

    def _recive_pending_payments(self, request_data, transaction=None):
        transaction_id = request_data["reference_sale"]
        transaction = Transaction(transaction_id)

        if not transaction.is_pending():
            error_info = {
                "request_data": request_data,
                "transaction": str(transaction.__dict__),
                "transaction_notification_data": transaction.get_notification_data(),
            }
            raise HttpException(
                *SysError.transaction_is_not_pending(), errors=error_info
            )

        request_payment_info = self.consult.by_reference_code(transaction_id)

        if (
            request_payment_info.get("code") != self.STATUS_SUCCESS
            or "result" not in request_payment_info
            or "payload" not in request_payment_info["result"]
            or len(request_payment_info["result"]["payload"]) < 1
        ):
            error_info = {
                "error": request_payment_info.get("error"),
                "request_data": request_data,
            }
            raise HttpException(*SysError.webhook_update_error(), errors=error_info)

        payment_info = request_payment_info["result"]["payload"][0]

        if "id" in payment_info:
            payment_info["PaymentId"] = payment_info["id"]

        events_to_update = list()
        webhook_status = None

        if payment_info["status"] == self.STATUS_DECLINED:
            events_to_update.append(EventHandler.NOT_AUTHORIZED_TRANSACTION_EVENT)
            webhook_status = WebhookHandler.PAYMENT_STATUS_NOT_AUTHORIZED
        elif payment_info["status"] == self.STATUS_AUTHORIZED:
            events_to_update.append(EventHandler.AUTHORIZED_TRANSACTION_EVENT)
            webhook_status = WebhookHandler.PAYMENT_STATUS_AUTHORIZED
        elif payment_info["status"] == self.CAPTURED:
            events_to_update.append(EventHandler.AUTHORIZED_TRANSACTION_EVENT)
            events_to_update.append(EventHandler.CAPTURED_TRANSACTION_EVENT)
            webhook_status = WebhookHandler.PAYMENT_STATUS_CAPTURED

        return transaction, events_to_update, webhook_status, payment_info

    def __create_acquirer_response(self, full_acquirer_response, successes_status):

        request_success = (
            True
            if full_acquirer_response.get("code") == self.STATUS_SUCCESS
            and "transactionResponse" in full_acquirer_response
            else False
        )
        if not request_success:
            return AcquirerResponse(
                full_acquirer_response.get("code"),
                full_acquirer_response,
                str(full_acquirer_response.get("error")),
                success=False,
                pending=False,
                antifraud=False,
            )

        full_acquirer_response = full_acquirer_response["transactionResponse"]

        success = (
            True if full_acquirer_response.get("state") in successes_status else False
        )

        pending = True if full_acquirer_response.get("state") == "PENDING" else False

        if (
            "transactionId" in full_acquirer_response
            and "orderId" in full_acquirer_response
        ):
            full_acquirer_response["PaymentId"] = "{}:{}".format(
                full_acquirer_response["orderId"],
                full_acquirer_response["transactionId"],
            )

        return AcquirerResponse(
            full_acquirer_response.get("responseCode"),
            full_acquirer_response,
            full_acquirer_response.get("responseMessage"),
            success=success,
            pending=pending,
            antifraud=True,
        )

    def __create_payment_data(self, transaction):
        payment_data = dict()

        order = dict()
        order["referenceCode"] = transaction["transaction_id"]
        order["description"] = "Cobrança da transação {}".format(
            transaction["transaction_id"]
        )
        order["language"] = "pt"

        payment_data["order"] = order

        t_payment = transaction["payment"]
        additional_values = dict()
        additional_values["TX_VALUE"] = dict()

        t_payment["amount"] = "{:02}".format(t_payment["amount"])
        additional_values["TX_VALUE"]["value"] = float(
            str(t_payment["amount"])[:-2] + "." + str(t_payment["amount"])[-2:]
        )
        additional_values["TX_VALUE"]["currency"] = "BRL"
        order["additionalValues"] = additional_values

        extra_parameters = dict()
        extra_parameters["INSTALLMENTS_NUMBER"] = t_payment["installments"]
        payment_data["extraParameters"] = extra_parameters

        buyer = dict()
        payer = dict()

        t_customer = transaction["customer"] if "customer" in transaction else None
        if t_customer:
            buyer["fullName"] = truncate(t_customer.get("name"), 150)
            buyer["emailAddress"] = t_customer.get("email")
            buyer["contactPhone"] = "({}){}".format(
                t_customer.get("phone")[:2], t_customer.get("phone")[2:]
            )
            buyer["dniNumber"] = t_customer.get("documentNumber")

            if buyer["dniNumber"]:
                buyer["dniNumber"] = mask_cpf_cnpj(buyer["dniNumber"])
            if t_customer.get("documentType") == "CNPJ":
                buyer["cnpj"] = t_customer.get("documentNumber")

            payer["emailAddress"] = t_customer.get("email")
            payer["fullName"] = t_customer.get("name")
            payer["contactPhone"] = t_customer.get("phone")
            payer["dniNumber"] = t_customer.get("documentNumber")

        shipping = dict()
        shipping["phone"] = buyer["contactPhone"]

        if "shipping" in transaction:
            t_shipping = transaction["shipping"]

            shipping["street1"] = truncate(t_shipping.get("street"), 100)
            shipping["city"] = t_shipping.get("city")
            shipping["state"] = t_shipping.get("state")
            shipping["country"] = truncate(t_shipping.get("country"), 2)
            shipping["postalCode"] = t_shipping.get("zipCode")

        elif t_customer and "address" in t_customer:
            t_shipping = t_customer["address"]

            shipping["street1"] = truncate(t_shipping.get("street"), 100)
            shipping["city"] = t_shipping.get("city")
            shipping["state"] = t_shipping.get("state")
            shipping["country"] = truncate(t_shipping.get("country"), 2)
            shipping["postalCode"] = t_shipping.get("zipCode")

        buyer["shippingAddress"] = shipping
        payer["billingAddress"] = shipping
        payment_data["order"]["buyer"] = buyer
        payment_data["payer"] = payer

        t_credit_card = transaction["creditCard"]
        credit_card = dict()

        if "token" in t_credit_card:
            credit_card["processWithoutCvv2"] = True
            payment_data["creditCardTokenId"] = t_credit_card["token"]
        else:
            if not t_customer or not t_customer.get("name"):
                buyer["fullName"] = t_credit_card.get("holderName")
                payer["fullName"] = t_credit_card.get("holderName")

            credit_card["number"] = t_credit_card["number"]
            credit_card["securityCode"] = t_credit_card["securityCode"]
            credit_card["expirationDate"] = "{}/{:02}".format(
                t_credit_card["expiryYear"], t_credit_card["expiryMonth"]
            )
            credit_card["name"] = t_credit_card["holderName"]
        payment_data["creditCard"] = credit_card

        payment_data["type"] = (
            "AUTHORIZATION_AND_CAPTURE"
            if t_payment["capture"] == CAPTURE_METHOD_SYNCHRONOUS
            else "AUTHORIZATION"
        )

        payment_method = t_credit_card["brand"]
        if payment_method == "master":
            payment_method = "mastercard"
        elif payment_method == "hiper":
            payment_method = "hipercard"

        payment_method = payment_method.upper()
        payment_data["paymentMethod"] = payment_method

        payment_data["paymentCountry"] = "BR"
        # payment_data["deviceSessionId"] = ''
        payment_data["ipAddress"] = "127.0.0.1"

        payment_data = {"transaction": payment_data}
        return payment_data

    def _create_card_token(self, transaction):
        t_credit_card = transaction["creditCard"]
        credit_card_data = dict()

        credit_card_data["creditCardToken"] = dict()
        credit_card_data["creditCardToken"]["payerId"] = transaction["clientAccountId"]
        if t_credit_card.get("holderName"):
            credit_card_data["creditCardToken"]["name"] = t_credit_card["holderName"]

        if (
            "customer" not in transaction
            or "documentNumber" not in transaction["customer"]
        ):
            raise Exception(
                "card owner document not found. To generate card token on PayU the document is required."
            )
        t_customer = transaction["customer"]
        credit_card_data["creditCardToken"]["payerId"] = t_customer["documentNumber"]
        credit_card_data["creditCardToken"]["identificationNumber"] = t_customer[
            "documentNumber"
        ]

        payment_method = t_credit_card["brand"]
        if payment_method == "master":
            payment_method = "mastercard"
        elif payment_method == "hiper":
            payment_method = "hipercard"

        credit_card_data["creditCardToken"]["paymentMethod"] = payment_method.upper()
        credit_card_data["creditCardToken"]["number"] = t_credit_card["number"]

        expirationDate = "{}/{:02}".format(
            t_credit_card["expiryYear"], t_credit_card["expiryMonth"]
        )

        credit_card_data["creditCardToken"]["expirationDate"] = expirationDate

        save_card_response = self.payu.create_token(credit_card_data)

        if save_card_response["code"] == self.STATUS_ERROR:
            raise Exception(save_card_response["error"])

        if save_card_response["code"] != self.STATUS_SUCCESS:
            raise Exception("Unexpected code returned when creating card token")

        acquirer_response = AcquirerResponse(
            save_card_response["code"],
            save_card_response,
            success=True,
        )

        return (
            save_card_response["creditCardToken"]["creditCardTokenId"],
            acquirer_response,
        )

    def __create_update_data(self, transaction, transaction_type):

        payment_data = dict()
        payment_data["transaction"] = dict()
        payment_data["transaction"]["order"] = dict()

        payment_data["language"] = "pt"
        order_and_transaction_id = transaction.get_payment_id().split(":")
        payment_data["transaction"]["order"]["id"] = order_and_transaction_id[0]
        payment_data["transaction"]["type"] = transaction_type
        payment_data["transaction"]["parentTransactionId"] = order_and_transaction_id[1]

        return payment_data
