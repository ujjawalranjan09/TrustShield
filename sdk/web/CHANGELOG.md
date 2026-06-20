# Changelog

## 1.1.0

### Added
- Retry with exponential backoff (3 retries, base 1s, max 10s) for all API requests
- `Verdict` interface matching the unified verdict schema from Phase D
- `analyzeImage()` method for QR code and fake payment screenshot detection
- `analyzeVoice()` method for voice transcript fraud analysis
- `SDK_VERSION` constant for version tracking

### Security
- Entity values are never logged raw in debug mode — redacted with `***` masking

## 1.0.0

### Added
- Initial release: `analyzeChat`, `scanMessage`, `reportEntity`, `lookupEntity`, `checkTransaction`, `healthCheck`
