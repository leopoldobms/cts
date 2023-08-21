from packages.common.constants import DEFAULT_PENDING_TRANSACTION_CODE


class HttpException(Exception):
    def __init__(
        self,
        message,
        code,
        http_code,
        errors=None,
        transaction_id=None,
        event_handler=None,
        error_event=None,
        event_data={},
        acquirer_info=None,
    ):
        self.response = {"message": message, "code": code}

        if acquirer_info:
            self.response["acquirer_info"] = acquirer_info

        if transaction_id is not None:
            self.response["transaction_id"] = transaction_id

        if code == DEFAULT_PENDING_TRANSACTION_CODE:
            self.response["antifraud"] = True

        if errors is not None:
            self.response["errors"] = errors

        self.http_code = http_code
        self.transaction_id = transaction_id
        self.event_handler = event_handler
        self.error_event = error_event
        self.event_data = event_data
