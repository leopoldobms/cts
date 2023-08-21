from marshmallow import (
    Schema,
    RAISE,
    fields,
    ValidationError,
    pre_load,
    validates_schema,
)
from marshmallow.validate import Length
from packages.common.general import remove_empty_elements


class CredentialAcquirerSchema(Schema):
    class Meta:
        unknown = RAISE

    acquirerCredentialId = fields.Int(required=True)
    acquirerName = fields.Str(required=True, validate=Length(max=80))
    mcc = fields.Str(required=True, validate=Length(max=10))
    credentials = fields.Field(required=True)

    @validates_schema
    def adyen_validate_credentials(self, data, **kwargs):
        acquirer = data["acquirerName"]
        credentials = data["credentials"]
        if acquirer == "adyen":
            if "merchant_account" not in credentials:
                raise ValidationError({"merchant_account": "Field not found."})
            if "username" not in credentials:
                raise ValidationError({"username": "Field not found."})
            if "password" not in credentials:
                raise ValidationError({"password": "Field not found."})

    @validates_schema
    def cielo_validate_credentials(self, data, **kwargs):
        acquirer = data["acquirerName"]
        credentials = data["credentials"]
        if acquirer == "cielo":
            if "merchant_id" not in credentials:
                raise ValidationError({"merchant_id": "Field not found."})
            if "merchant_key" not in credentials:
                raise ValidationError({"merchant_key": "Field not found."})

    @validates_schema
    def mercadopago_validate_credentials(self, data, **kwargs):
        acquirer = data["acquirerName"]
        credentials = data["credentials"]
        if acquirer == "mercadopago":
            if "public_key" not in credentials:
                raise ValidationError({"public_key": "Field not found."})
            if "access_token" not in credentials:
                raise ValidationError({"access_token": "Field not found."})

    @validates_schema
    def payu_validate_credentials(self, data, **kwargs):
        acquirer = data["acquirerName"]
        credentials = data["credentials"]
        if acquirer == "payu":
            if "api_login" not in credentials:
                raise ValidationError({"api_login": "Field not found."})
            if "api_key" not in credentials:
                raise ValidationError({"api_key": "Field not found."})
            if "merchant_id" not in credentials:
                raise ValidationError({"merchant_id": "Field not found."})
            if "account_id" not in credentials:
                raise ValidationError({"account_id": "Field not found."})
