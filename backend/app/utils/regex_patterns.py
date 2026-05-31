import re

# UPI VPA pattern: handle@provider format
# Valid UPI providers include ybl, okaxis, oksbi, okhdfcbank, paytm, ibl, etc.
UPI_PROVIDERS = r'(?:ybl|okaxis|oksbi|okhdfcbank|paytm|ibl|axl|upi|apl|ratn|indus|kotak|sbi|hdfcbank|icici|axisbank|fbl|boi|pnb|cnrb|idfcfirst|jupiteraxis)'
UPI_PATTERN = re.compile(
    rf'[\w.-]+@{UPI_PROVIDERS}',
    re.IGNORECASE
)

# Phone numbers: Indian format with optional country code and spaces/dashes
PHONE_PATTERN = re.compile(
    r'(?:\+91[\s-]?|91[\s-]?|0)?[789]\d[\s-]?\d{4}[\s-]?\d{4}\b'
)

# AnyDesk ID: 9-digit number preceded by contextual keywords
ANYDESK_PATTERN = re.compile(
    r'(?:anydesk|any\s*desk|remote\s*access)\s*(?:id|code|number)?[\s:]*(\d{9,10})\b',
    re.IGNORECASE
)

# TeamViewer ID: 9-10 digit number preceded by contextual keywords
TEAMVIEWER_PATTERN = re.compile(
    r'(?:teamviewer|team\s*viewer)\s*(?:id|code|number)?[\s:]*(\d{9,10})\b',
    re.IGNORECASE
)

# URL shortlinks (common services used in phishing)
URL_SHORTLINK_PATTERN = re.compile(
    r'(?:https?://)?(?:bit\.ly|tinyurl\.com|t\.co|goo\.gl|is\.gd|rb\.gy|cutt\.ly|short\.io|ow\.ly)/[\w\-]+',
    re.IGNORECASE
)

# IFSC code: 4 uppercase letters + 0 + 6 alphanumeric chars (word boundaries, not anchors)
IFSC_PATTERN = re.compile(r'\b[A-Z]{4}0[A-Z0-9]{6}\b')

# APK file links/references
APK_PATTERN = re.compile(r'(?:https?://\S+)?\.apk\b', re.IGNORECASE)
