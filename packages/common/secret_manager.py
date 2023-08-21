from packages.common.constants import AWS_SECRETS_NAME, AWS_REGION
import boto3
import base64
import json


def init():
    global secret_manager
    secret_manager = SecretManager()


class SecretManager:
    def __init__(self):
        session = boto3.session.Session()
        client = session.client(service_name="secretsmanager", region_name=AWS_REGION)

        try:
            get_secrets = client.get_secret_value(SecretId=AWS_SECRETS_NAME)
        except Exception as e:
            raise Exception("Error while getting secrets on AWS. ", e)

        if "SecretString" in get_secrets:
            self.secrets = json.loads(get_secrets["SecretString"])
        else:
            self.secrets = json.loads(base64.b64decode(get_secrets["SecretBinary"]))

    def get_secret(self, secret_name):
        if secret_name not in self.secrets:
            raise Exception("secret {} not in Secret Manager.".format(secret_name))
        return self.secrets[secret_name]
