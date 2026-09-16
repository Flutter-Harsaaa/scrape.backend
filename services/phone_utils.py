import re
import phonenumbers
from phonenumbers import NumberParseException
from phonenumbers.phonenumberutil import PhoneNumberType


def normalize_phone(raw: str | None) -> str | None:
    """
    Normalize an international phone number to E.164 format.

    Google Places' internationalPhoneNumber should normally be supplied,
    so no country-specific assumption is required.
    """
    if not raw:
        return None

    try:
        number = phonenumbers.parse(raw, None)

        if not phonenumbers.is_valid_number(number):
            return None

        return phonenumbers.format_number(
            number,
            phonenumbers.PhoneNumberFormat.E164,
        )

    except NumberParseException:
        return None


def classify_phone(raw: str | None) -> str:
    """
    Classify a phone number as mobile, landline, or unknown.
    Works with international numbers.
    """
    if not raw:
        return "unknown"

    try:
        number = phonenumbers.parse(raw, None)

        if not phonenumbers.is_valid_number(number):
            return "unknown"

        number_type = phonenumbers.number_type(number)

        if number_type in (
            PhoneNumberType.MOBILE,
            PhoneNumberType.FIXED_LINE_OR_MOBILE,
        ):
            return "mobile"

        if number_type == PhoneNumberType.FIXED_LINE:
            return "landline"

        return "unknown"

    except NumberParseException:
        return "unknown"