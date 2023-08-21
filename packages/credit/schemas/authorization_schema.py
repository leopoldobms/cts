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
from packages.common.general import remove_empty_elements, remove_accents
from packages.credit.schemas.additional_data_schema import AdditionalDataSchema

## credit authorization transaction schema
class PaymentSchema(Schema):
    class Meta:
        unknown = RAISE

    amount = fields.Int(required=True, strict=True, validate=Range(min=1, max=90000000))
    currency = fields.Str(required=True, validate=OneOf(["BRL"]))
    installments = fields.Int(strict=True, validate=Range(min=1, max=12), missing=1)
    capture = fields.Str(
        validate=OneOf(["NO", "ASYNCHRONOUS", "SYNCHRONOUS"]), missing="NO"
    )
    softDescriptor = fields.Str(validate=Length(max=13), missing="CENTERPAG")

    @pre_load
    def remove_accents(self, data, **kwargs):
        if "softDescriptor" in data:
            data["softDescriptor"] = remove_accents(data["softDescriptor"])
        return data


class CreditCardSchema(Schema):
    class Meta:
        unknown = RAISE

    brand = fields.Str(
        required=True,
        validate=OneOf(
            [
                "visa",
                "master",
                "amex",
                "elo",
                "aura",
                "jcb",
                "diners",
                "discover",
                "hiper",
            ]
        ),
    )
    holderName = fields.Str(required=True, validate=Length(max=40))
    number = fields.Str(required=True, validate=Length(max=19, min=13))
    expiryMonth = fields.Int(required=True, strict=True, validate=Range(min=1, max=12))
    expiryYear = fields.Int(
        required=True,
        strict=True,
        validate=Range(min=datetime.datetime.now().year, max=2120),
    )
    securityCode = fields.Str(required=True, validate=Length(max=4, min=3))

    @validates_schema
    def validate_expiration_date(self, data, **kwargs):
        current_year = datetime.datetime.now().year
        current_month = datetime.datetime.now().month
        if data["expiryYear"] == current_year and data["expiryMonth"] < current_month:
            raise ValidationError({"expirationDate": "Credit Card Expired"})


class CreditCardWithTokenSchema(Schema):
    class Meta:
        unknown = RAISE

    brand = fields.Str(
        required=True,
        validate=OneOf(
            [
                "visa",
                "master",
                "amex",
                "elo",
                "aura",
                "jcb",
                "diners",
                "discover",
                "hiper",
            ]
        ),
    )
    token = fields.Str(required=True)


class AddressSchema(Schema):
    class Meta:
        unknown = RAISE

    street = fields.Str(required=True, validate=Length(max=255))
    number = fields.Int(required=True, strict=True, validate=Range(min=0, max=9999999))
    complement = fields.Str(validate=Length(max=50))
    zipCode = fields.Str(required=True, validate=Regexp("^[0-9]{5}-[0-9]{3}$"))
    city = fields.Str(required=True, validate=Length(max=50))
    state = fields.Str(validate=Length(equal=2))
    country = fields.Str(required=True, validate=Length(max=35))


class CustomerSchema(Schema):
    class Meta:
        unknown = RAISE

    name = fields.Str(validate=Length(max=255))
    email = fields.Email(validate=Length(max=255))
    documentType = fields.Str(validate=OneOf(["CPF", "RG", "CNH", "CNPJ"]))
    documentNumber = fields.Str(validate=Regexp("^[0-9]{11,15}$"))
    phone = fields.Str(validate=Regexp("^[0-9]{10,15}$"))
    address = fields.Nested(AddressSchema)


class SubsellerSchema(Schema):
    class Meta:
        unknown = RAISE

    id = fields.Str(required=True, max=15)
    name = fields.Str(validate=Length(max=255), required=True)
    documentNumber = fields.Str(validate=Regexp("^[0-9]{11,15}$"), required=True)
    address = fields.Nested(AddressSchema, required=True)


class ProductSchema(Schema):
    class Meta:
        unknown = RAISE

    category = fields.Str(validate=Length(max=19))
    reference = fields.Str(validate=Length(max=30))


class NotificationSchema(Schema):
    class Meta:
        unknown = RAISE

    url = fields.Str(required=True, validate=Length(max=180))
    login = fields.Str(required=True, validate=Length(max=300))
    password = fields.Str(required=True, validate=Length(max=300))


class CreditAuthorizationSchema(Schema):
    class Meta:
        unknown = RAISE

    transaction_id = fields.Str(required=True, validate=Length(max=80))
    reference = fields.Str(required=True, validate=Length(max=80))
    credentialAcquirer = fields.Field(required=True)
    payment = fields.Nested(PaymentSchema, required=True)
    creditCard = fields.Nested(CreditCardSchema, required=True)
    customer = fields.Nested(CustomerSchema, allow_none=True)
    shipping = fields.Nested(AddressSchema, allow_none=True)
    subSeller = fields.Nested(SubsellerSchema, allow_none=True)
    product = fields.Nested(ProductSchema, allow_none=True)
    clientAccountId = fields.Str(required=True, validate=Length(max=40))
    notification = fields.Nested(NotificationSchema, allow_none=True)
    additionalData = fields.Nested(AdditionalDataSchema, allow_none=True)
    live = fields.Field(required=True)
    notificationItems = fields.Field(required=True)

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


class CreditAuthorizationWithTokenSchema(CreditAuthorizationSchema):
    class Meta:
        unknown = RAISE

    creditCard = fields.Nested(CreditCardWithTokenSchema, required=True)
