from __future__ import division
from packages.common.custom_exceptions import HttpException
from packages.common.errors import SysError
from http import HTTPStatus
import json
import datetime
from unicodedata import normalize


def datetime_handler(x):
    import datetime

    if isinstance(x, datetime.datetime):
        return x.isoformat()
    raise TypeError("Unknown type")


def diff_current_date(event_date):
    current_time_utc = datetime.datetime.utcnow()
    return current_time_utc - event_date


def remove_empty_elements(d, allow_empty_string=True):
    """recursively remove empty lists, empty dicts, or None elements from a dictionary"""

    def empty(x):
        return x is None or x == {} or x == [] or ()

    if not isinstance(d, (dict, list)):
        if isinstance(d, str) and not allow_empty_string:
            s = d.strip()
            if s == "":
                return None
        return d
    elif isinstance(d, list):
        return [
            v
            for v in (remove_empty_elements(v, allow_empty_string) for v in d)
            if not empty(v)
        ]
    else:
        return {
            k: v
            for k, v in (
                (k, remove_empty_elements(v, allow_empty_string)) for k, v in d.items()
            )
            if not empty(v)
        }


def dict_raise_on_duplicates(ordered_pairs):
    """Reject duplicate keys for json loads."""
    d = {}
    for k, v in ordered_pairs:
        if k in d:
            raise HttpException(*SysError.duplicated_keys_json_request())
        else:
            d[k] = v
    return d


def obfuscate_creditcard(credit_card_dict):
    if "number" not in credit_card_dict or not isinstance(
        credit_card_dict["number"], str
    ):
        return credit_card_dict

    credit_card_dict["number"] = (
        credit_card_dict["number"][:6] + "xxxxxx" + credit_card_dict["number"][-4:]
    )

    if "securityCode" in credit_card_dict:
        del credit_card_dict["securityCode"]

    return credit_card_dict


def remove_accents(text):
    return normalize("NFKD", text).encode("ASCII", "ignore").decode("ASCII")


def mask_cpf_cnpj(text):
    if not text or len(text) not in [11, 14]:
        return None
    elif len(text) == 11:
        return "{}{}{}.{}{}{}.{}{}{}-{}{}".format(*text)
    else:
        return "{}{}.{}{}{}.{}{}{}/{}{}{}{}-{}{}".format(*text)


def truncate(text, size):
    return text[:size] if isinstance(text, str) else text
