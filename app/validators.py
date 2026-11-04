"""Phone number validation utilities following E.164 and Indian mobile rules."""
import re
from typing import Tuple, Optional


def validate_phone_number(raw_phone: str) -> Tuple[bool, Optional[str], str]:
    """
    Validate phone number:
    - Strips whitespace, hyphens, and parenthesis.
    - Requires E.164 format: leading '+' followed by 8 to 15 digits.
    - If country code is +91 (India), requires exactly 10 digits starting with 6, 7, 8, or 9.
    
    Returns:
        (is_valid, error_message, cleaned_phone)
    """
    if not raw_phone:
        return False, "Phone number is required.", ""

    cleaned = re.sub(r"[\s\-\(\)\.]", "", raw_phone)

    # Must start with '+'
    if not cleaned.startswith("+"):
        return False, "Phone number must include country code starting with '+' (e.g. +91 98765 43210).", cleaned

    digits_only = cleaned[1:]

    # Must contain only digits after '+'
    if not digits_only.isdigit():
        return False, "Phone number must contain only numbers after the '+' country code.", cleaned

    # E.164 digit length bounds: 8 to 15 digits
    if len(digits_only) < 8:
        return False, "Phone number is too short (minimum 8 digits including country code).", cleaned
    if len(digits_only) > 15:
        return False, "Phone number is too long (maximum 15 digits including country code).", cleaned

    # Specific rule for India (+91)
    if cleaned.startswith("+91"):
        national_number = cleaned[3:]
        if len(national_number) != 10:
            return False, "Indian phone numbers (+91) must have exactly 10 digits after +91.", cleaned
        if national_number[0] not in "6789":
            return False, "Indian mobile numbers must start with 6, 7, 8, or 9.", cleaned

    return True, None, cleaned

