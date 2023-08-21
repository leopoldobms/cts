import json
import sys
import copy
import string
import random
from marshmallow import ValidationError
import pytest

sys.path.insert(1, "../../../")
from packages.credit.schemas.authorization_schema import CreditAuthorizationSchema
from app import app

# unit tests for authorization request for credit transactions - field validations - required fields
# https://monetizze.atlassian.net/browse/PAY-29
# if a new field became required, add it to required fields dict and create a new test

required_fields = {
    "transaction_id": "ce89960f-3909-4708-b239-f2c6ea010292",
    "reference": "your order reference",
    "payment": {"amount": 1234, "currency": "BRL"},
    "creditCard": {
        "number": "5124484565953521",
        "expiryMonth": 2,
        "expiryYear": 2030,
        "securityCode": "737",
    },
    "clientAccountId": "66eaf963-bc7f-412c-8284-003945e5eb79",
}

# support funciton - recive a path from field and delete it - ex: payment.amount
def remove_required_field(path):
    required_fields_field_delected = copy.deepcopy(required_fields)
    routes = path.split(".")
    last_route = routes[-1]
    pointer = required_fields_field_delected

    for route in routes:
        if route != last_route:
            pointer = pointer[route]
    del pointer[last_route]

    return required_fields_field_delected


# all tests from specific required field do the same thing.
# so, they call the same function with the path that we will delete :)
def required_field_test(path_field_remove):
    credit_authorization_schema = CreditAuthorizationSchema()
    dict_without_field = remove_required_field(path_field_remove)

    with pytest.raises(ValidationError) as exception_data:
        credit_authorization_schema.load(dict_without_field)
    exception_info = json.loads(str(exception_data.value).replace("'", '"'))

    assert "errors" in exception_info
    pointer = exception_info["errors"]

    routes = path_field_remove.split(".")
    for route in routes:
        pointer = pointer[route]

    assert pointer[0] == "Missing data for required field."


def test_required_field_reference():
    path_field_remove = "reference"
    required_field_test(path_field_remove)


def test_required_field_payment():
    path_field_remove = "payment"
    required_field_test(path_field_remove)


def test_required_field_payment_amount():
    path_field_remove = "payment.amount"
    required_field_test(path_field_remove)


def test_required_field_payment_currency():
    path_field_remove = "payment.currency"
    required_field_test(path_field_remove)


def test_required_field_creditcard():
    path_field_remove = "creditCard"
    required_field_test(path_field_remove)


def test_required_field_creditcard_number():
    path_field_remove = "creditCard.number"
    required_field_test(path_field_remove)


def test_required_field_creditcard_expirymonth():
    path_field_remove = "creditCard.expiryMonth"
    required_field_test(path_field_remove)


def test_required_field_creditcard_expiryyear():
    path_field_remove = "creditCard.expiryYear"
    required_field_test(path_field_remove)


def test_required_field_creditcard_securitycode():
    path_field_remove = "creditCard.securityCode"
    required_field_test(path_field_remove)


def test_required_field_clientAccountId():
    path_field_remove = "clientAccountId"
    required_field_test(path_field_remove)


def test_required_only_required():
    credit_authorization_schema = CreditAuthorizationSchema()
    credit_authorization_schema.load(required_fields)
    assert isinstance(credit_authorization_schema, CreditAuthorizationSchema)


def test_required_all_none():
    credit_authorization_schema = CreditAuthorizationSchema()
    required_fields_all_none = copy.deepcopy(required_fields)

    for key in required_fields_all_none:
        required_fields_all_none[key] = None

    with pytest.raises(ValidationError) as exception_data:
        credit_authorization_schema.load(required_fields_all_none)

    exception_info = json.loads(str(exception_data.value).replace("'", '"'))
    assert "errors" in exception_info
    assert len(exception_info["errors"]) == len(required_fields)


def test_required_all_empty():
    credit_authorization_schema = CreditAuthorizationSchema()
    required_fields_all_none = copy.deepcopy(required_fields)

    for key in required_fields_all_none:
        required_fields_all_none[key] = ""

    with pytest.raises(ValidationError) as exception_data:
        credit_authorization_schema.load(required_fields_all_none)

    exception_info = json.loads(str(exception_data.value).replace("'", '"'))
    assert "errors" in exception_info
    assert len(exception_info["errors"]) == len(required_fields)


def test_required_empty_json():
    credit_authorization_schema = CreditAuthorizationSchema()
    empty_data = "{}"

    with pytest.raises(ValidationError) as exception_data:
        credit_authorization_schema.load(empty_data)
    exception_info = json.loads(str(exception_data.value).replace("'", '"'))

    assert "errors" in exception_info
    assert "_schema" in exception_info["errors"]
    assert exception_info["errors"]["_schema"][0] == "Invalid input type."


# optional fields test
optional_fields = {
    "payment": {
        "installments": 2,
        "capture": "SYNCHRONOUS",
        "softDescriptor": "CTS é TOP",
    },
    "creditCard": {"holderName": "Payments Melhor Time"},
    "customer": {
        "name": "Comprador Crédito Completo",
        "email": "compradorteste@teste.com",
        "documentType": "CPF",
        "documentNumber": "12312312312",
        "phone": "35999999999",
        "address": {
            "street": "Rua Teste",
            "number": 123,
            "complement": "AP 123",
            "zipCode": "31325-457",
            "city": "Belo Horizonte",
            "state": "MG",
            "country": "BRA",
        },
    },
    "shipping": {
        "street": "Rua Teste",
        "number": 123,
        "complement": "AP 123",
        "zipCode": "31325-457",
        "city": "Belo Horizonte",
        "state": "MG",
        "country": "BRA",
    },
    "product": {"category": "digital_content"},
}


def test_required_try_only_optionals():
    credit_authorization_schema = CreditAuthorizationSchema()
    with pytest.raises(ValidationError) as exception_data:
        credit_authorization_schema.load(optional_fields)

    exception_info = json.loads(str(exception_data.value).replace("'", '"'))
    assert "errors" in exception_info
    assert len(exception_info["errors"]) == len(required_fields)


# suport function - merge required and optional fields
# if you dont any custom fields, it uses the default optionals and required
def dict_with_required_and_optionals(
    custom_required_fields=None, custom_optional_fields=None
):

    required_fields_copy = (
        copy.deepcopy(required_fields)
        if custom_required_fields is None
        else copy.deepcopy(custom_required_fields)
    )

    optional_fields_copy = (
        copy.deepcopy(optional_fields)
        if custom_optional_fields is None
        else copy.deepcopy(custom_optional_fields)
    )

    for key in optional_fields_copy:
        if key in required_fields_copy:
            required_fields_copy[key] = {
                **required_fields_copy[key],
                **optional_fields_copy[key],
            }
        else:
            required_fields_copy[key] = optional_fields_copy[key]
    return required_fields_copy


# suport function - replace all optional fields with some value
def replace_all_optionals(value):
    optional_fields_copy = copy.deepcopy(optional_fields)

    for key in optional_fields_copy:
        if not isinstance(optional_fields_copy[key], dict):
            optional_fields_copy[key] = value
        else:
            for subkey in optional_fields_copy[key]:
                optional_fields_copy[key][subkey] = value

    return optional_fields_copy


def test_required_all_optionals_as_none():

    optional_fields_none = replace_all_optionals(None)
    required_and_optionals = dict_with_required_and_optionals(
        custom_optional_fields=optional_fields_none
    )

    credit_authorization_schema = CreditAuthorizationSchema()
    credit_authorization_schema.load(required_and_optionals)
    assert isinstance(credit_authorization_schema, CreditAuthorizationSchema)


def test_required_all_optionals_as_empty():
    optional_fields_none = replace_all_optionals("")
    required_and_optionals = dict_with_required_and_optionals(
        custom_optional_fields=optional_fields_none
    )

    credit_authorization_schema = CreditAuthorizationSchema()
    credit_authorization_schema.load(required_and_optionals)
    assert isinstance(credit_authorization_schema, CreditAuthorizationSchema)


# get a list of fields, replace their value and validates:
# string size, number (greater or lower), set, one of and mask
def replace_and_test(fields_to_replace, assertion_type):
    dict_replace = dict_with_required_and_optionals()

    for field in fields_to_replace:
        routes = field["path_field"].split(".")
        last_route = routes[-1]
        pointer = dict_replace

        for route in routes:
            if route != last_route:
                pointer = pointer[route]

        pointer[last_route] = field["value"]

    credit_authorization_schema = CreditAuthorizationSchema()
    with pytest.raises(ValidationError) as exception_data:
        credit_authorization_schema.load(dict_replace)
    exception_info = json.loads(str(exception_data.value).replace("'", '"'))

    assert "errors" in exception_info
    errors = exception_info["errors"]

    for field in fields_to_replace:
        pointer = errors
        routes = field["path_field"].split(".")
        for route in routes:
            pointer = pointer[route]

        pointer = pointer[0]
        if assertion_type == "str_greater":
            assert (
                "Length must be" in pointer or "Longer than maximum length" in pointer
            )
        elif assertion_type == "num_greater":
            assert "Must be greater than or equal" in pointer
        elif assertion_type == "num_lower":
            assert "less than or equal" in pointer
        elif assertion_type == "one_of":
            assert "Must be one of" in pointer
        elif assertion_type == "mask":
            assert "String does not match expected pattern." in pointer


def generate_random_string(size):
    return "".join(
        random.choices(
            string.ascii_uppercase + string.digits + string.ascii_lowercase, k=size
        )
    )


def test_size_greater_string_fields():
    fields_to_replace = []
    fields_to_replace.append(
        {"path_field": "reference", "value": generate_random_string(81)}
    )
    fields_to_replace.append(
        {"path_field": "payment.softDescriptor", "value": generate_random_string(14)}
    )
    fields_to_replace.append(
        {"path_field": "creditCard.number", "value": generate_random_string(20)}
    )
    fields_to_replace.append(
        {"path_field": "creditCard.securityCode", "value": generate_random_string(5)}
    )
    fields_to_replace.append(
        {"path_field": "creditCard.holderName", "value": generate_random_string(31)}
    )
    fields_to_replace.append(
        {"path_field": "clientAccountId", "value": generate_random_string(41)}
    )
    fields_to_replace.append(
        {"path_field": "customer.name", "value": generate_random_string(256)}
    )
    fields_to_replace.append(
        {
            "path_field": "customer.email",
            "value": generate_random_string(246) + "@teste.com",
        }
    )
    fields_to_replace.append(
        {"path_field": "customer.documentNumber", "value": generate_random_string(16)}
    )
    fields_to_replace.append(
        {
            "path_field": "customer.address.complement",
            "value": generate_random_string(51),
        }
    )
    fields_to_replace.append(
        {"path_field": "customer.address.city", "value": generate_random_string(51)}
    )
    fields_to_replace.append(
        {"path_field": "customer.address.state", "value": generate_random_string(3)}
    )
    fields_to_replace.append(
        {"path_field": "customer.address.country", "value": generate_random_string(36)}
    )
    replace_and_test(fields_to_replace, "str_greater")


def test_greater_number_fields():
    fields_to_replace = []
    fields_to_replace.append({"path_field": "payment.amount", "value": 100000001})
    fields_to_replace.append({"path_field": "creditCard.expiryMonth", "value": 13})
    fields_to_replace.append({"path_field": "creditCard.expiryYear", "value": 2121})
    fields_to_replace.append({"path_field": "payment.installments", "value": 13})
    replace_and_test(fields_to_replace, "num_greater")


def test_lower_number_fields():
    fields_to_replace = []
    fields_to_replace.append({"path_field": "payment.amount", "value": 0})
    fields_to_replace.append({"path_field": "creditCard.expiryMonth", "value": 0})
    fields_to_replace.append({"path_field": "creditCard.expiryYear", "value": 2019})
    fields_to_replace.append({"path_field": "payment.installments", "value": 0})
    replace_and_test(fields_to_replace, "num_lower")


def test_one_of_fields():
    fields_to_replace = []
    fields_to_replace.append({"path_field": "payment.currency", "value": "USD"})
    fields_to_replace.append(
        {"path_field": "payment.capture", "value": "NOTVALIDCAPTUREMETHOD"}
    )
    fields_to_replace.append({"path_field": "customer.documentType", "value": "RFA"})
    replace_and_test(fields_to_replace, "one_of")


def test_mask_fields():
    fields_to_replace = []
    fields_to_replace.append(
        {"path_field": "customer.address.zipCode", "value": "92930940"},
    )
    fields_to_replace.append(
        {"path_field": "customer.phone", "value": generate_random_string(16)}
    )
    replace_and_test(fields_to_replace, "mask")


def test_mask_zipCode():
    fields_to_replace = []
    fields_to_replace.append(
        {"path_field": "customer.address.zipCode", "value": "9293-0940"},
    )
    replace_and_test(fields_to_replace, "mask")


# request validations
@pytest.fixture
def client():
    app.config["TESTING"] = True
    client = app.test_client()

    yield client


def test_request_cielo_authorize_success(client):
    dict_post = dict_with_required_and_optionals()
    res = client.post("v1/credit/cielo/authorize", json=dict_post)
    assert res.status_code >= 200 and res.status_code <= 299


def test_request_cielo_authorize_error(client):
    res = client.post("v1/credit/cielo/authorize", json=optional_fields)
    assert res.status_code >= 400 and res.status_code <= 499
