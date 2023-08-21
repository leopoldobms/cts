class AcquirersInterface:
    """docstring for ClassName"""

    def _authorize(self, transaction):
        raise NotImplementedError

    def _cancel(self):
        raise NotImplementedError

    def _capture(self):
        raise NotImplementedError

    def _consult(self):
        raise NotImplementedError

    # identifier of the acquirer on db
    def _get_identifier(self):
        raise NotImplementedError

    def get_days_to_expire_authorization(self):
        raise NotImplementedError
