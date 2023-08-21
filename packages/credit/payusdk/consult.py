from packages.credit.payusdk.client import PayuClient
from packages.credit.payusdk.commands import PING, ORDER_DETAIL_BY_REFERENCE_CODE
import json


class Consult(PayuClient):
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

        self.url = "{}/reports-api/{}/service.cgi".format(
            self.url, self.payments_api_version
        )

    # check if the service payments is working
    def ping(self):
        payload = {"command": PING}
        return self._post(self.url, json=payload)

    def by_reference_code(self, reference_code):
        payment_data = {
            "command": ORDER_DETAIL_BY_REFERENCE_CODE,
            "details": {"referenceCode": reference_code},
        }
        return self._post(self.url, json=payment_data)

