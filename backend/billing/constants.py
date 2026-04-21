import re

# Shared billing ID patterns — import from here, never redefine
# Using fullmatch() so no ^ or $ anchors needed
USER_ID_PATTERN = re.compile(r"[a-zA-Z0-9_-]{8,64}")
CUSTOMER_ID_PATTERN = re.compile(r"cus_[a-zA-Z0-9]{14,24}")
PRICE_ID_PATTERN = re.compile(r"price_[a-zA-Z0-9]{14,24}")

