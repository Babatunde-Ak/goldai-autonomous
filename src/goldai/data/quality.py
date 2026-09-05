from __future__ import annotations

from enum import Enum


class DataQualityStatus(str, Enum):
    VALID = "VALID"
    MALFORMED = "MALFORMED"
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
    BID_ABOVE_ASK = "BID_ABOVE_ASK"
    EXTREME_SPREAD = "EXTREME_SPREAD"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
