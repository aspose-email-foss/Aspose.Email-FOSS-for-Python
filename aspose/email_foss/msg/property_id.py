from __future__ import annotations

from enum import IntEnum

from .property_tags import CommonMessagePropertyId
from .property_types import PropertyTypeCode


class PropertyId(IntEnum):
    """Common property identifiers paired with their default MAPI property types."""

    def __new__(cls, property_id: int | CommonMessagePropertyId, property_type: int | PropertyTypeCode):
        normalized_property_id = int(property_id)
        obj = int.__new__(cls, normalized_property_id)
        obj._value_ = normalized_property_id
        obj.property_type = int(property_type)
        return obj

    MESSAGE_CLASS = (CommonMessagePropertyId.MESSAGE_CLASS, PropertyTypeCode.PTYP_STRING)
    TRANSPORT_MESSAGE_HEADERS = (CommonMessagePropertyId.TRANSPORT_MESSAGE_HEADERS, PropertyTypeCode.PTYP_STRING)
    SUBJECT = (CommonMessagePropertyId.SUBJECT, PropertyTypeCode.PTYP_STRING)
    DISPLAY_TO = (CommonMessagePropertyId.DISPLAY_TO, PropertyTypeCode.PTYP_STRING)
    DISPLAY_CC = (CommonMessagePropertyId.DISPLAY_CC, PropertyTypeCode.PTYP_STRING)
    DISPLAY_BCC = (CommonMessagePropertyId.DISPLAY_BCC, PropertyTypeCode.PTYP_STRING)
    INTERNET_MESSAGE_ID = (CommonMessagePropertyId.INTERNET_MESSAGE_ID, PropertyTypeCode.PTYP_STRING)
    MESSAGE_FLAGS = (CommonMessagePropertyId.MESSAGE_FLAGS, PropertyTypeCode.PTYP_INTEGER32)
    INTERNET_CODEPAGE = (CommonMessagePropertyId.INTERNET_CODEPAGE, PropertyTypeCode.PTYP_INTEGER32)
    SENDER_NAME = (CommonMessagePropertyId.SENDER_NAME, PropertyTypeCode.PTYP_STRING)
    SENDER_ADDRESS_TYPE = (CommonMessagePropertyId.SENDER_ADDRESS_TYPE, PropertyTypeCode.PTYP_STRING)
    SENDER_EMAIL_ADDRESS = (CommonMessagePropertyId.SENDER_EMAIL_ADDRESS, PropertyTypeCode.PTYP_STRING)
    MESSAGE_DELIVERY_TIME = (CommonMessagePropertyId.MESSAGE_DELIVERY_TIME, PropertyTypeCode.PTYP_TIME)
    STORE_SUPPORT_MASK = (CommonMessagePropertyId.STORE_SUPPORT_MASK, PropertyTypeCode.PTYP_INTEGER32)
    BODY = (CommonMessagePropertyId.BODY, PropertyTypeCode.PTYP_STRING)
    BODY_HTML = (CommonMessagePropertyId.BODY_HTML, PropertyTypeCode.PTYP_BINARY)
    DISPLAY_NAME = (CommonMessagePropertyId.DISPLAY_NAME, PropertyTypeCode.PTYP_STRING)
    ATTACH_METHOD = (CommonMessagePropertyId.ATTACH_METHOD, PropertyTypeCode.PTYP_INTEGER32)
    ATTACH_DATA_BINARY = (CommonMessagePropertyId.ATTACH_DATA_BINARY, PropertyTypeCode.PTYP_BINARY)
    ATTACH_FILENAME = (CommonMessagePropertyId.ATTACH_FILENAME, PropertyTypeCode.PTYP_STRING)
    ATTACH_LONG_FILENAME = (CommonMessagePropertyId.ATTACH_LONG_FILENAME, PropertyTypeCode.PTYP_STRING)
    ATTACH_MIME_TAG = (CommonMessagePropertyId.ATTACH_MIME_TAG, PropertyTypeCode.PTYP_STRING)
    ATTACH_CONTENT_ID = (CommonMessagePropertyId.ATTACH_CONTENT_ID, PropertyTypeCode.PTYP_STRING)
    SCHEDULE_INFO_DELEGATE_NAMES = (CommonMessagePropertyId.SCHEDULE_INFO_DELEGATE_NAMES, PropertyTypeCode.PTYP_MULTIPLE_STRING)
    SCHEDULE_INFO_MONTHS_BUSY = (CommonMessagePropertyId.SCHEDULE_INFO_MONTHS_BUSY, PropertyTypeCode.PTYP_MULTIPLE_INTEGER32)
    EXAMPLE_TAG_100A = (CommonMessagePropertyId.EXAMPLE_TAG_100A, PropertyTypeCode.PTYP_BINARY)
    EXAMPLE_TAG_101D = (CommonMessagePropertyId.EXAMPLE_TAG_101D, PropertyTypeCode.PTYP_BINARY)
