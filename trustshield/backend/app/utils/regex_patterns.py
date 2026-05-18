import re

UPI_PATTERN = re.compile(r'[\w.-]+@[\w.-]+')
PHONE_PATTERN = re.compile(r'(?:\+91|91)?[789]\d{9}')
ANYDESK_PATTERN = re.compile(r'\b\d{9}\b')
TEAMVIEWER_PATTERN = re.compile(r'\b\d{9,10}\b')
URL_SHORTLINK_PATTERN = re.compile(r'(bit\.ly|tinyurl\.com|t\.co)/\w+')
IFSC_PATTERN = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')
APK_PATTERN = re.compile(r'\.apk\b', re.IGNORECASE)
