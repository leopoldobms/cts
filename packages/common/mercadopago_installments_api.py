import requests
from packages.common.constants import URL_INSTALLMENTS_MERCADOPAGO
from http import HTTPStatus


class MercadopagoInstallmentsApi:
    def get_brand_info(bin, token, request_brand, amount=1):

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(token),
        }
        params = {
            "bin": bin,
            "amount": amount,
        }

        response = requests.get(
            URL_INSTALLMENTS_MERCADOPAGO, params=params, headers=headers
        )

        response_json = response.json()
        if (
            response.status_code >= HTTPStatus.OK
            and response.status_code < HTTPStatus.MULTIPLE_CHOICES
        ):
            payment_type_id = []
            for v in response_json:
                if "credit_card" in v.get("payment_type_id"):
                    index = response_json.index(v)

                payment_type_id.append(v.get("payment_type_id"))

            if "credit_card" in payment_type_id:
                brand = response_json[index]
            else:
                raise Exception("payment method is invalid.")
        else:
            brand = dict()
            brand["payment_method_id"] = request_brand

        return brand
