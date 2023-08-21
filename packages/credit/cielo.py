from cieloApi3Mon import *
from iso3166 import countries
from packages.credit.acquirer import Acquirer, AcquirerResponse
from packages.common.cryptography import Cryptography
from packages.common.constants import (
    DEVELOPMENT_ENVIRONMENTS,
    APP_ENV,
    CAPTURE_METHOD_SYNCHRONOUS
)
from packages.common.custom_exceptions import HttpException
from packages.common.errors import SysError

class Cielo(Acquirer):
    """docstring for ClassName"""

    # identifier of cielo on db
    def _get_identifier(self):
        return 1

    def __init__(self, credentials):
        super(Cielo, self).__init__()
        credentials = credentials["credentials"]
        cryptography = Cryptography()
        self.environment = Environment(sandbox=APP_ENV in DEVELOPMENT_ENVIRONMENTS)
        self.merchant = Merchant(
            cryptography.decrypt(credentials["merchant_id"]),
            cryptography.decrypt(credentials["merchant_key"])
        )
        self.cielo_ecommerce = CieloEcommerce(self.merchant, self.environment)

        self.POSSIBLE_RESPONSE_STATUSES = {
            "NotFinished": 0,
            "Authorized": 1,
            "PaymentConfirmed": 2,
            "Denied": 3,
            "Voided": 10,
            "Refunded": 11,
            "Pending": 12,
            "Aborted": 13,
            "Scheduled": 20,
        }

    def get_days_to_expire_authorization(self):
        return 15

    def _authorize(self, transaction):
        sale = self.__create_sale(transaction)
        created_sale_response = self.cielo_ecommerce.create_sale(sale)
        payment_response = created_sale_response["Payment"]

        return self.__create_acquirer_response(
            payment_response,
            [
                self.POSSIBLE_RESPONSE_STATUSES["Authorized"],
                self.POSSIBLE_RESPONSE_STATUSES["PaymentConfirmed"],
            ],
        )

    def _cancel(self, transaction):
        response_cancel_sale = self.cielo_ecommerce.cancel_sale(
            transaction.get_payment_id(), transaction.get_amount()
        )
        return self.__create_acquirer_response(
            response_cancel_sale,
            [
                self.POSSIBLE_RESPONSE_STATUSES["Voided"],
                self.POSSIBLE_RESPONSE_STATUSES["Refunded"],
            ],
        )

    def _capture(self, transaction):
        response_capture_sale = self.cielo_ecommerce.capture_sale(
            transaction.get_payment_id(), transaction.get_amount(), 0
        )

        return self.__create_acquirer_response(
            response_capture_sale, [self.POSSIBLE_RESPONSE_STATUSES["PaymentConfirmed"]]
        )

    def _consult(self, transaction):
        return self.cielo_ecommerce.get_sale(transaction.get_payment_id())

    def _create_card_token(self, transaction):
        t_credit_card = transaction["creditCard"]

        credit_card = CreditCard(t_credit_card["securityCode"], t_credit_card["brand"])
        credit_card.expiration_date = self.__create_card_expiration_date(
            t_credit_card["expiryMonth"], t_credit_card["expiryYear"]
        )
        credit_card.card_number = t_credit_card["number"]
        credit_card_holder = t_credit_card.get("holderName")
        if isinstance(credit_card_holder, str):
            credit_card_holder = credit_card_holder[:25]
        credit_card.holder = credit_card_holder
        credit_card.customer_name = transaction["customer"]["name"]

        response_create_card_token = self.cielo_ecommerce.create_card_token(credit_card)

        acquirer_response = AcquirerResponse(
            "OK", response_create_card_token, success=True,
        )

        return response_create_card_token["CardToken"], acquirer_response

    def __create_acquirer_response(self, full_acquirer_response, successes_status):
        success = (
            True if full_acquirer_response["Status"] in successes_status else False
        )

        return AcquirerResponse(
            full_acquirer_response["ReturnCode"],
            full_acquirer_response,
            full_acquirer_response["ReturnMessage"],
            success,
        )

    def __create_sale(self, transaction):
        sale = Sale(transaction["transaction_id"])

        customer = Customer(None)

        if "customer" in transaction:
            t_customer = transaction["customer"]

            customer.name = t_customer.get("name")
            customer.email = t_customer.get("email")
            customer.identity_type = t_customer.get("documentType")
            identity = t_customer.get("documentNumber")
            if isinstance(identity, str):
                identity = identity[0:14]
            customer.identity = identity

            if "address" in t_customer:
                customer_address = Address()
                t_customer_address = t_customer["address"]

                customer_address.street = t_customer_address.get("street")
                customer_address.number = t_customer_address.get("number")
                customer_address.complement = t_customer_address.get("complement")
                customer_address.zip_code = t_customer_address.get("zipCode")
                customer_address.city = t_customer_address.get("city")
                customer_address.state = t_customer_address.get("state")
                customer_address.country = t_customer_address.get("country", "BRA")

                customer.address = customer_address

        if "shipping" in transaction:
            t_shipping = transaction["shipping"]
            shipping = Address()

            shipping.street = t_shipping.get("street")
            shipping.number = t_shipping.get("number")
            shipping.complement = t_shipping.get("complement")
            shipping.zip_code = t_shipping.get("zipCode")
            shipping.city = t_shipping.get("city")
            shipping.state = t_shipping.get("state")
            shipping.country = t_shipping.get("country", "BRA")

            customer.delivery_adress = shipping

        sale.customer = customer

        t_credit_card = transaction["creditCard"]
        if "token" in t_credit_card:
            credit_card = CreditCard(None, t_credit_card["brand"])
            credit_card.card_token = t_credit_card["token"]
        else:
            credit_card = CreditCard(
                t_credit_card["securityCode"], t_credit_card["brand"]
            )
            credit_card.expiration_date = self.__create_card_expiration_date(
                t_credit_card["expiryMonth"], t_credit_card["expiryYear"]
            )
            credit_card.card_number = t_credit_card["number"]
            credit_card_holder = t_credit_card.get("holderName")
            if isinstance(credit_card_holder, str):
                credit_card_holder = credit_card_holder[:25]
            credit_card.holder = credit_card_holder

        t_payment = transaction["payment"]
        payment = Payment(t_payment["amount"], t_payment["installments"])
        payment.soft_descriptor = t_payment["softDescriptor"]
        payment.currency = t_payment["currency"]

        if (
            "additionalData" in transaction
            and "paymentFacilitator" in transaction["additionalData"]
        ):
            t_payment_facilitator = transaction["additionalData"]["paymentFacilitator"]
            t_payment_facilitator_address = transaction["additionalData"][
                "paymentFacilitator"
            ]["address"]

            payment_facilitator = PaymentFacilitator()
            sub_establishment = SubEstablishment()

            payment_facilitator.establishment_code = t_payment_facilitator[
                "establishmentCode"
            ]
            sub_establishment.establishment_code = t_payment_facilitator["shopperId"]
            sub_establishment.identity = t_payment_facilitator["identity"]
            sub_establishment.mcc = t_payment_facilitator["mcc"]
            sub_establishment.phone_number = t_payment_facilitator["phoneNumber"]
            sub_establishment.city = t_payment_facilitator_address["city"]
            sub_establishment.state = t_payment_facilitator_address["state"]
            sub_establishment.postal_code = "".join(
                filter(str.isdigit, t_payment_facilitator_address["zipCode"])
            )
            payment.soft_descriptor = t_payment_facilitator["name"][:13]

            country = countries.get(t_payment_facilitator_address["country"])
            sub_establishment.country_code = country.numeric

            sub_establishment.address = (
                t_payment_facilitator_address["street"][
                    : 22 - len(str(t_payment_facilitator_address["number"])) + 1
                ]
                + ","
                + str(t_payment_facilitator_address["number"])
            )

            payment_facilitator.sub_establishment = sub_establishment

            sale.payment_facilitator = payment_facilitator

        if t_payment["capture"] == CAPTURE_METHOD_SYNCHRONOUS:
            payment.capture = True

        payment.credit_card = credit_card
        sale.payment = payment

        return sale

    def __create_card_expiration_date(self, expiry_month, expiry_year):
        expiry_month = (
            str(expiry_month) if expiry_month > 9 else "0" + str(expiry_month)
        )
        return expiry_month + "/" + str(expiry_year)
