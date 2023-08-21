import mercadopagoCTS as mercadopago
import json
from iso3166 import countries
from packages.common.errors import SysError
from packages.common.custom_exceptions import HttpException
from packages.credit.acquirer import Acquirer, AcquirerResponse
from packages.common.cryptography import Cryptography
from packages.common.constants import (
    DEVELOPMENT_ENVIRONMENTS,
    APP_ENV,
    CAPTURE_METHOD_SYNCHRONOUS,
)
from packages.common.general import remove_empty_elements
from packages.common.transaction import Transaction
from packages.common.event_handler import EventHandler
from packages.common.storage import Storage
from http import HTTPStatus
from packages.common.errors import SysError
from packages.common.webhook_handler import WebhookHandler
from packages.common.database import Database
from packages.common.mercadopago_installments_api import MercadopagoInstallmentsApi


class Mercadopago(Acquirer):
    """docstring for ClassName"""

    # identifier of mercadopago on db
    def _get_identifier(self):
        return 3

    def __init__(self, credentials):
        super(Mercadopago, self).__init__()

        self.credentials = credentials
        credentials = credentials["credentials"]
        cryptography = Cryptography()

        self.mp_public_key = cryptography.decrypt(credentials["public_key"])
        self.mp_access_token = cryptography.decrypt(credentials["access_token"])

        self.mercadopago = mercadopago.MP(self.mp_access_token)

        # if APP_ENV in DEVELOPMENT_ENVIRONMENTS:
        #     self.mercadopago.sandbox_mode(True)

        self.DAYS_TO_CANCEL = 180
        self.STATUS_PENDING = "pending"
        self.STATUS_APPROVED = "approved"
        self.STATUS_AUTHORIZED = "authorized"
        self.STATUS_IN_PROCESS = "in_process"
        self.STATUS_IN_MEDIATION = "in_mediation"
        self.STATUS_REJECTED = "rejected"
        self.STATUS_CANCELLED = "cancelled"
        self.STATUS_REFUNDED = "refunded"
        self.STATUS_CHARGED_BACK = "charged_back"

    def get_days_to_expire_authorization(self):
        return 5

    def _authorize(self, transaction):
        payment_data = self.__create_payment_data(transaction)

        device_fingerprint = (
            transaction["additionalData"]["deviceFingerprint"]
            if "additionalData" in transaction
            and "deviceFingerprint" in transaction["additionalData"]
            else None
        )

        if device_fingerprint:
            extra_headers = {"X-meli-session-id": device_fingerprint}
        else:
            extra_headers = None

        response = self.mercadopago.post(
            "/v1/payments", payment_data, extra_headers=extra_headers
        )

        return self.__create_acquirer_response(
            response["response"], [self.STATUS_AUTHORIZED, self.STATUS_APPROVED]
        )

    def _cancel(self, transaction):
        if not transaction.can_cancel(self.DAYS_TO_CANCEL):
            raise HttpException(
                *SysError.cannot_cancel(),
                transaction_id=transaction.get_transaction_id(),
            )

        payment_id = transaction.get_payment_id()
        if not transaction.is_captured():
            payment_data = {"status": "cancelled"}
            response = self.mercadopago.put(f"/v1/payments/{payment_id}", payment_data)
            return self.__create_acquirer_response(
                response["response"], [self.STATUS_CANCELLED]
            )
        else:
            response = self.mercadopago.refund_payment(str(payment_id))
            if response["status"] == 201:
                response["response"]["status"] = self.STATUS_REFUNDED
            return self.__create_acquirer_response(
                response["response"], [self.STATUS_REFUNDED]
            )

    def _capture(self, transaction):
        payment_id = transaction.get_payment_id()
        payment_data = {"capture": True}
        response = self.mercadopago.put(f"/v1/payments/{payment_id}", payment_data)

        return self.__create_acquirer_response(
            response["response"], [self.STATUS_APPROVED], retry=True
        )

    def _consult(self, transaction):
        return {}

    def _create_card_token(self, transaction):
        t_credit_card = transaction["creditCard"]

        if "customer" not in transaction or "email" not in transaction["customer"]:
            raise Exception(
                "card owner email not found. To generate card token on MP email is required."
            )

        t_customer = transaction["customer"]
        credit_card_token = self.__create_card_token_js(t_credit_card, t_customer)

        # mp requires that you create a customer (or use one) and save his card token to make it permanent
        # with this process you create a card_id and with the card_id you can generate a card token anytime
        search_customer_data = {"email": t_customer["email"]}
        customer_exists_response = self.mercadopago.get(
            "/v1/customers/search", search_customer_data
        )

        if customer_exists_response["status"] != HTTPStatus.OK:
            raise Exception(customer_exists_response["response"])

        if customer_exists_response["response"]["results"]:
            # customer already exists in MP. so we get his id.
            if len(customer_exists_response["response"]["results"]) > 1:
                raise Exception(
                    "More than one customer registred on MP with same email {}.".format(
                        t_customer["email"]
                    )
                )

            customer_id = customer_exists_response["response"]["results"][0]["id"]
        else:
            # create new customer
            customer_identification = None
            if (
                "documentType" in t_customer
                and "documentNumber" in t_customer
                and t_customer["documentType"] in ["CPF", "CNPJ"]
            ):
                customer_identification = {
                    "type": t_customer["documentType"],
                    "number": t_customer["documentNumber"],
                }

            create_customer_data = {
                "email": t_customer["email"],
                "first_name": t_customer.get("name"),
                "identification": customer_identification,
            }

            create_customer_response = self.mercadopago.post(
                "/v1/customers", create_customer_data
            )

            if create_customer_response["status"] != HTTPStatus.CREATED:
                raise Exception(create_customer_response["response"])

            customer_id = create_customer_response["response"]["id"]

        # save the card for this customer
        credit_card_data = dict()
        brand_info_response = MercadopagoInstallmentsApi.get_brand_info(
            t_credit_card["number"][:6], self.mp_access_token, t_credit_card["brand"]
        )

        if brand_info_response and "issuer" in brand_info_response:
            credit_card_data["issuer_id"] = int(brand_info_response["issuer"]["id"])

        credit_card_data["payment_method_id"] = brand_info_response["payment_method_id"]

        credit_card_data["token"] = credit_card_token

        save_card_response = create_customer_response = self.mercadopago.post(
            "/v1/customers/{}/cards".format(customer_id), credit_card_data
        )

        if save_card_response["status"] not in [HTTPStatus.OK, HTTPStatus.CREATED]:
            raise Exception(create_customer_response["response"])

        acquirer_response = AcquirerResponse(
            save_card_response["status"],
            create_customer_response["response"],
            success=True,
        )

        # we need the customer_id to use the saved_card, so, your token = card_id-customer_id:
        saved_card_token = "{}-{}".format(
            save_card_response["response"]["id"], customer_id
        )

        return saved_card_token, acquirer_response

    def _recive_pending_payments(self, request_data, transaction=None):
        mp_transaction_id = request_data["data"]["id"]
        request_payment_info = self.mercadopago.get_payment(mp_transaction_id)

        if request_payment_info["status"] > 299:
            raise HttpException(
                *SysError.webhook_update_error(), errors=request_payment_info
            )

        payment_info = request_payment_info["response"]

        if "id" in payment_info:
            payment_info["PaymentId"] = payment_info["id"]

        events_to_update = list()
        webhook_status = None

        if payment_info["status"] == "rejected":
            events_to_update.append(EventHandler.NOT_AUTHORIZED_TRANSACTION_EVENT)
            webhook_status = WebhookHandler.PAYMENT_STATUS_NOT_AUTHORIZED
        elif payment_info["status"] == "authorized":
            events_to_update.append(EventHandler.AUTHORIZED_TRANSACTION_EVENT)
            webhook_status = WebhookHandler.PAYMENT_STATUS_AUTHORIZED
        elif payment_info["status"] == "approved":
            events_to_update.append(EventHandler.AUTHORIZED_TRANSACTION_EVENT)
            events_to_update.append(EventHandler.CAPTURED_TRANSACTION_EVENT)
            webhook_status = WebhookHandler.PAYMENT_STATUS_CAPTURED

        return transaction, events_to_update, webhook_status, payment_info

    def __create_acquirer_response(
        self, full_acquirer_response, successes_status, retry=False
    ):
        success = (
            True
            if "status" in full_acquirer_response
            and full_acquirer_response["status"] in successes_status
            else False
        )
        response_code = full_acquirer_response["status"]
        message = ""
        pending = False

        if full_acquirer_response["status"] == "in_process":
            pending = True

        if "id" in full_acquirer_response:
            full_acquirer_response["PaymentId"] = full_acquirer_response["id"]

        if "status_detail" in full_acquirer_response:
            response_code = full_acquirer_response["status_detail"]
            message = full_acquirer_response["status"]

        elif (
            "cause" in full_acquirer_response
            and type(full_acquirer_response["cause"]) == list
            and full_acquirer_response["cause"]
            and "code" in full_acquirer_response["cause"][0]
            and full_acquirer_response["cause"][0]["code"]
        ):
            response_code = full_acquirer_response["cause"][0]["code"]
            message = full_acquirer_response["cause"][0].get("description")

        elif "error" in full_acquirer_response and full_acquirer_response["error"]:
            response_code = full_acquirer_response["error"]
            message = full_acquirer_response["message"]

        elif "message" in full_acquirer_response:
            response_code = full_acquirer_response["message"]
            message = full_acquirer_response["status"]

        return AcquirerResponse(
            response_code,
            full_acquirer_response,
            message,
            success,
            pending,
            True,
            retry=retry,
        )

    def __create_payment_data(self, transaction):
        payment_data = dict()
        msg_body = transaction["notificationItems"][0]["NotificationRequestItem"]
        allowed_events = ["CANCEL_OR_REFUND", "CAPTURE"]
        if msg_body["eventCode"] in allowed_events:
            print("entrou")

        t_credit_card = transaction["creditCard"]

        if "token" in t_credit_card:
            brand_info_response = self.get_brand_db(transaction["cardToken"])
            token_info = t_credit_card["token"].split("-")
            t_credit_card["token"] = token_info[0]
            token_info.remove(t_credit_card["token"])
            customer_id = "-".join(token_info)

        t_customer = transaction["customer"] if "customer" in transaction else None

        payment_data["token"] = self.__create_card_token_js(t_credit_card, t_customer)

        t_payment = transaction["payment"]
        payment_data["installments"] = t_payment["installments"]
        t_payment["amount"] = "{:02}".format(t_payment["amount"])
        payment_data["transaction_amount"] = float(
            str(t_payment["amount"])[:-2] + "." + str(t_payment["amount"])[-2:]
        )
        payment_data[
            "description"
        ] = "Cobrança da transação: {}, referência externa: {}".format(
            transaction["transaction_id"], transaction["reference"]
        )

        t_additional_data = (
            transaction["additionalData"] if "additionalData" in transaction else None
        )

        payment_method_id = t_credit_card["brand"]
        if payment_method_id == "hiper":
            payment_method_id = "hipercard"

        if "token" not in t_credit_card:
            brand_info_response = MercadopagoInstallmentsApi.get_brand_info(
                t_credit_card["number"][:6],
                self.mp_access_token,
                payment_method_id,
                payment_data["transaction_amount"],
            )

        payment_data["payment_method_id"] = brand_info_response["payment_method_id"]

        if t_customer:
            payer = dict()
            payer["email"] = t_customer.get("email")
            payer["identification"] = dict()
            payer["identification"]["type"] = t_customer.get("documentType")
            payer["identification"]["number"] = t_customer.get("documentNumber")

            if "phone" in t_customer:
                payer_phone = dict()
                payer_phone["area_code"] = t_customer["phone"][:2]
                payer_phone["number"] = t_customer["phone"][2:]

                # payer["phone"] = payer_phone

            if "name" in t_customer:
                customer_names = t_customer["name"].split(" ")
                if len(customer_names) > 1:
                    payer["first_name"] = customer_names[0]
                    payer["last_name"] = customer_names[-1]

            payment_data["payer"] = payer

        if "token" in t_credit_card:
            payer = dict()
            payer["type"] = "customer"
            payer["id"] = customer_id

            payment_data["payer"] = payer

        payment_data["binary_mode"] = False
        payment_data["external_reference"] = transaction["transaction_id"]
        payment_data["statement_descriptor"] = t_payment["softDescriptor"]
        payment_data["capture"] = (
            True if t_payment["capture"] == CAPTURE_METHOD_SYNCHRONOUS else False
        )

        additional_info = dict()
        if t_customer:
            additional_info["payer"] = dict()
            if "first_name" in payer:
                additional_info["payer"]["first_name"] = payer["first_name"]
                additional_info["payer"]["last_name"] = payer["last_name"]

            if "phone" in t_customer:
                additional_info["payer"]["phone"] = payer_phone

            if "address" in t_customer:
                payer_address = dict()
                t_payer_address = t_customer["address"]

                payer_address["zip_code"] = t_payer_address.get("zipCode")
                payer_address["street_name"] = t_payer_address.get("street")
                payer_address["street_number"] = t_payer_address.get("number")

                additional_info["payer"]["address"] = payer_address

            if "shipping" in transaction:
                t_shipping = transaction["shipping"]
                shipping = dict()

                shipping["zip_code"] = t_shipping.get("zipCode")
                shipping["state_name"] = t_shipping.get("state")
                shipping["city_name"] = t_shipping.get("city")
                shipping["street_name"] = t_shipping.get("street")
                shipping["street_number"] = t_shipping.get("number")

                additional_info["shipments"] = dict()
                additional_info["shipments"]["receiver_address"] = shipping

            if "product" in transaction:
                t_product = transaction["product"]
                if t_product.get("reference"):
                    payment_data["description"] = "{}, referência produto: {}".format(
                        payment_data["description"], t_product.get("reference")
                    )

        if t_additional_data:
            if (
                "paymentFacilitator" in t_additional_data
                and "mcc" in t_additional_data["paymentFacilitator"]
            ):
                payment_data["metadata"] = dict()
                payment_data["metadata"]["mcc"] = t_additional_data[
                    "paymentFacilitator"
                ]["mcc"]

        payment_data["additional_info"] = additional_info

        return payment_data

    def __create_card_token_js(self, t_credit_card, t_customer):
        token_data = dict()

        # create card token for a card that is not saved by _create_card_token method
        if "token" not in t_credit_card:
            token_data["card_number"] = t_credit_card["number"]
            token_data["expiration_year"] = t_credit_card["expiryYear"]
            token_data["expiration_month"] = t_credit_card["expiryMonth"]
            token_data["security_code"] = t_credit_card["securityCode"]

            token_data["cardholder"] = dict()

            if t_credit_card.get("holderName"):
                token_data["cardholder"]["name"] = t_credit_card["holderName"]

            if t_customer:
                token_data["cardholder"]["identification"] = dict()

            if not t_credit_card.get("holderName") and t_customer.get("name"):
                token_data["cardholder"]["name"] = t_customer["name"][:30]

                t_customer_document_type = t_customer.get("documentType")
                if t_customer_document_type in ["CPF", "CNPJ"] and t_customer.get(
                    "documentNumber"
                ):
                    token_data["cardholder"]["identification"]["type"] = t_customer[
                        "documentType"
                    ]
                    token_data["cardholder"]["identification"]["number"] = t_customer[
                        "documentNumber"
                    ]
        else:
            token_data = {"card_id": t_credit_card["token"]}

        mp_response = self.mercadopago.post(
            "/v1/card_tokens?public_key={}".format(self.mp_public_key), token_data
        )
        return mp_response["response"]["id"]

    @staticmethod
    def get_brand_db(card_token):
        try:
            db = Database()
            generated_token_event_data = db.select(
                "te.event_data->>'$.acquirer_response.payment_method.id' as payment_method_id",
                "transactionid_cardtoken tc",
                [
                    "join transaction_event te on (tc.transaction_id = te.transaction_id) and te.event_type ='generatedCardTokenEvent'"
                ],
                {
                    "tc.card_token": card_token,
                },
            )
            brand = generated_token_event_data[0]
            brand["payment_method_id"] = brand["payment_method_id"].lower()
        except:
            brand = None
        return brand
