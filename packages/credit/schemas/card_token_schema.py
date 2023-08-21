import datetime
from marshmallow import (
    Schema,
    RAISE,
    fields,
    ValidationError,
    pre_load,
    validates_schema,
)
from marshmallow.validate import Length, Range, OneOf, Regexp
from packages.credit.schemas.authorization_schema import CreditCardSchema
from packages.common.general import remove_empty_elements


class CreditCardForTokenSchema(CreditCardSchema):
    class Meta:
        unknown = RAISE

    holderName = fields.Str(required=True, validate=Length(max=40))


class CustomerSchema(Schema):
    class Meta:
        unknown = RAISE

    name = fields.Str(required=True, validate=Length(max=255))
    email = fields.Email(validate=Length(max=255))
    documentType = fields.Str(validate=OneOf(["CPF", "RG", "CNH", "CNPJ"]))
    documentNumber = fields.Str(validate=Regexp("^[0-9]{11,15}$"))


class CreditCardTokenSchema(Schema):
    class Meta:
        unknown = RAISE

    credentialAcquirer = fields.Field(required=True)
    creditCard = fields.Nested(CreditCardForTokenSchema, required=True)
    customer = fields.Nested(CustomerSchema, required=True)
    clientAccountId = fields.Str(required=True, validate=Length(max=40))

    @pre_load
    def pre_process(self, data, many, **kwargs):
        if isinstance(data, dict):
            data = remove_empty_elements(data, allow_empty_string=False)
        return data

    def handle_error(self, exc, data, **kwargs):
        if (
            isinstance(data, dict)
            and "transaction_id" in data
            and data["transaction_id"]
        ):
            transaction_id = data["transaction_id"]
        else:
            transaction_id = ""
        raise ValidationError(
            {"transaction_id": transaction_id, "errors": exc.messages}
        )
