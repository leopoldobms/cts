from packages.credit.payusdk.client import PayuClient
from packages.credit.payusdk.commands import PING, SUBMIT_TRANSACTION, CREATE_TOKEN
import json


class Payments(PayuClient):
    def __init__(
        self,
        api_login,
        api_key,
        merchant_id,
        account_id,
        payments_api_version="4.0",
        sandbox=False,
    ):
        super().__init__(
            api_login,
            api_key,
            merchant_id,
            account_id,
            payments_api_version=payments_api_version,
            sandbox=sandbox,
        )

        self.url = "{}/payments-api/{}/service.cgi".format(
            self.url, self.payments_api_version
        )

    # check if the service payments is working
    def ping(self):
        payload = {"command": PING}
        return self._post(self.url, json=payload)

    def authorize(self, payment_data):
        payment_data["transaction"]["order"]["accountId"] = self.account_id
        reference = payment_data["transaction"]["order"]["referenceCode"]
        tx_value = payment_data["transaction"]["order"]["additionalValues"]["TX_VALUE"][
            "value"
        ]
        currency = payment_data["transaction"]["order"]["additionalValues"]["TX_VALUE"][
            "currency"
        ]

        payment_data["transaction"]["order"]["signature"] = self._get_signature(
            reference, tx_value, currency
        )

        payment_data = {"command": SUBMIT_TRANSACTION, **payment_data}
        return self._post(self.url, json=payment_data)

    def create_token(self, token_data):
        token_data = {"command": CREATE_TOKEN, **token_data}
        return self._post(self.url, json=token_data)

    def update_transaction(self, payment_data):
        payment_data = {"command": SUBMIT_TRANSACTION, **payment_data}

        return self._post(self.url, json=payment_data)
