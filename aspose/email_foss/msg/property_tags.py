from __future__ import annotations

from enum import IntEnum


class CommonMessagePropertyId(IntEnum):
    """Common MAPI property identifiers used by the MSG reader/writer for core message semantics."""

    # Property id for message class string such as IPM.Note.
    MESSAGE_CLASS = 0x001A
    # Property id for transport header block string used to project RFC-style headers.
    TRANSPORT_MESSAGE_HEADERS = 0x007D
    # Property id for message subject text.
    SUBJECT = 0x0037
    # Property id for display-form To recipients string.
    DISPLAY_TO = 0x0E04
    # Property id for display-form Cc recipients string.
    DISPLAY_CC = 0x0E03
    # Property id for display-form Bcc recipients string.
    DISPLAY_BCC = 0x0E02
    # Property id for Internet Message-ID string.
    INTERNET_MESSAGE_ID = 0x1035
    # Property id for Message object status flags.
    MESSAGE_FLAGS = 0x0E07
    # Property id for the code page used for the body or HTML body.
    INTERNET_CODEPAGE = 0x3FDE
    # Property id for sender display name.
    SENDER_NAME = 0x0C1A
    # Property id for sender address type string, typically SMTP.
    SENDER_ADDRESS_TYPE = 0x0C1E
    # Property id for sender SMTP-style email address.
    SENDER_EMAIL_ADDRESS = 0x0C1F
    # Property id for message delivery FILETIME value.
    MESSAGE_DELIVERY_TIME = 0x0E06
    # Property id for store support mask that controls Unicode string expectations in MSG files.
    STORE_SUPPORT_MASK = 0x340D
    # Property id for plain-text body value.
    BODY = 0x1000
    # Property id for HTML body value.
    BODY_HTML = 0x1013
    # Property id for generic display name fields used in several MSG object contexts.
    DISPLAY_NAME = 0x3001
    # Property id for attachment method classification (for example regular file versus embedded message).
    ATTACH_METHOD = 0x3705
    # Property id for binary attachment payload stream.
    ATTACH_DATA_BINARY = 0x3701
    # Property id for short attachment file name.
    ATTACH_FILENAME = 0x3704
    # Property id for long attachment file name.
    ATTACH_LONG_FILENAME = 0x3707
    # Property id for attachment MIME type tag string.
    ATTACH_MIME_TAG = 0x370E
    # Property id for attachment content-id string.
    ATTACH_CONTENT_ID = 0x3712
    # Property id referenced by MSG variable-length multi-valued stream naming example (__substg1.0_6844101F).
    SCHEDULE_INFO_DELEGATE_NAMES = 0x6844
    # Property id referenced by MSG fixed-length multi-valued stream naming example (__substg1.0_68531003).
    SCHEDULE_INFO_MONTHS_BUSY = 0x6853
    # Property id referenced by MSG variable-length stream naming example (__substg1.0_100A0102).
    EXAMPLE_TAG_100A = 0x100A
    # Property id referenced by MSG variable-length stream naming example (__substg1.0_101D0102).
    EXAMPLE_TAG_101D = 0x101D
