import requests
import hashlib


class PayuClient(object):
    TEST_BASE = "https://sandbox.api.payulatam.com"
    PROD_BASE = "https://api.payulatam.com"

    def __init__(
        self,
        api_login,
        api_key,
        merchant_id,
        account_id,
        payments_api_version="4.0",
        sandbox=False,
    ):

        self.api_login = api_login
        self.api_key = api_key
        self.merchant_id = merchant_id
        self.account_id = account_id

        self.language = "en"
        self.payments_api_version = payments_api_version

        self.sandbox = sandbox
        self.url = self.TEST_BASE if self.is_sandbox else self.PROD_BASE

    @property
    def is_sandbox(self):
        return self.sandbox

    def _get(self, url, **kwargs):
        return self._request("GET", url, **kwargs)

    def _post(self, url, **kwargs):

        if('json' in kwargs and isinstance(kwargs['json'],dict)):
            kwargs['json']['test'] = self.sandbox
            kwargs['json']['language'] = self.language
            kwargs['json']['merchant'] = dict()
            kwargs['json']['merchant']['apiLogin'] = self.api_login
            kwargs['json']['merchant']['apiKey'] = self.api_key

        return self._request("POST", url, **kwargs)

    def _put(self, url, **kwargs):
        return self._request("PUT", url, **kwargs)

    def _delete(self, url, **kwargs):
        return self._request("DELETE", url, **kwargs)

    def _request(self, method, url, headers=None, **kwargs):
        """
        Normally the connection guarantees response times of 3 seconds on average,
        if there is an abnormal situation, the maximum response time is 1 minute.
        It is highly recommended that you set “timeouts” when you connect with PayU.
        Args:
            method:
            url:
            headers:
            **kwargs:
        Returns:
        """
        _headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if headers:
            _headers.update(headers)

        return self._parse(
            requests.request(method, url, headers=_headers, timeout=60, **kwargs)
        )

    def _parse(self, response):
        if (
            "Content-Type" in response.headers
            and "application/json" in response.headers["Content-Type"]
        ):
            r = response.json()
        else:
            r = response.text
        return r

    def _get_signature(self, reference_code, tx_value, currency):
        signature = '{}~{}~{}~{}~{}'.format(self.api_key, self.merchant_id, reference_code, tx_value, currency)
        return hashlib.md5(signature.encode('utf')).hexdigest()