from cryptography.fernet import Fernet
from packages.common.secret_manager import secret_manager
from packages.common.constants import CRYPTHOGRAPHY_SALT


class Cryptography:
    def __init__(self):
        self.fernet_key = secret_manager.get_secret("FERNET_KEY")
        self.fernet = Fernet(self.fernet_key)

    def encrypt(self, value):
        value = "{}-{}".format(value, CRYPTHOGRAPHY_SALT)
        token = self.fernet.encrypt(bytes(value, "utf-8"))
        return token.decode("utf-8")

    def decrypt(self, token):
        value = self.fernet.decrypt(bytes(token, "utf-8")).decode("utf-8")
        return value[: len(value) - len(CRYPTHOGRAPHY_SALT) - 1]
