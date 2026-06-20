import Foundation

/// TrustShield iOS SDK
///
/// Provides fraud detection capabilities for iOS payment apps:
/// - Real-time message scanning
/// - Session monitoring
/// - Overlay/remote access detection
/// - Behavioral signal collection
/// - Image and voice analysis
/// - Offline queue for pending requests
///
/// Usage:
/// ```swift
/// let trustShield = TrustShield(apiKey: "your-key", baseUrl: "https://api.trustshield.io")
/// let result = await trustShield.scanMessage("Share your OTP batao")
/// print(result.riskLevel) // "HIGH"
/// ```
public class TrustShield {

    public static let sdkVersion = "1.1.0"

    public struct Config {
        public var baseUrl: String
        public var apiKey: String
        public var timeout: TimeInterval
        public var maxRetries: Int

        public init(
            baseUrl: String = "http://localhost:8000",
            apiKey: String = "",
            timeout: TimeInterval = 5.0,
            maxRetries: Int = 3
        ) {
            self.baseUrl = baseUrl
            self.apiKey = apiKey
            self.timeout = timeout
            self.maxRetries = maxRetries
        }
    }

    // MARK: - Types

    public struct ChatMessage: Codable {
        public let sender: String
        public let text: String

        public init(sender: String, text: String) {
            self.sender = sender
            self.text = text
        }
    }

    public struct SessionMetadata: Codable {
        public let clientAppId: String
        public let sessionId: String
        public let contactInitiatedBy: String
        public let isDuringActiveUpiSession: Bool
        public let userDeviceHash: String
        public var priorReportsForSender: Int?

        enum CodingKeys: String, CodingKey {
            case clientAppId = "client_app_id"
            case sessionId = "session_id"
            case contactInitiatedBy = "contact_initiated_by"
            case isDuringActiveUpiSession = "is_during_active_upi_session"
            case userDeviceHash = "user_device_hash"
            case priorReportsForSender = "prior_reports_for_sender"
        }

        public init(
            clientAppId: String,
            sessionId: String,
            contactInitiatedBy: String,
            isDuringActiveUpiSession: Bool,
            userDeviceHash: String,
            priorReportsForSender: Int? = nil
        ) {
            self.clientAppId = clientAppId
            self.sessionId = sessionId
            self.contactInitiatedBy = contactInitiatedBy
            self.isDuringActiveUpiSession = isDuringActiveUpiSession
            self.userDeviceHash = userDeviceHash
            self.priorReportsForSender = priorReportsForSender
        }
    }

    public struct AnalyzeRequest: Codable {
        public let messages: [ChatMessage]
        public let sessionMetadata: SessionMetadata

        enum CodingKeys: String, CodingKey {
            case messages
            case sessionMetadata = "session_metadata"
        }
    }

    public struct AnalyzeResponse: Codable {
        public let sessionId: String
        public let riskScore: Int
        public let riskLevel: String
        public let recommendedAction: String
        public let flaggedEntities: [FlaggedEntity]
        public let warningMessageEn: String?
        public let warningMessageHi: String?
        public let interventionType: String

        enum CodingKeys: String, CodingKey {
            case sessionId = "session_id"
            case riskScore = "risk_score"
            case riskLevel = "risk_level"
            case recommendedAction = "recommended_action"
            case flaggedEntities = "flagged_entities"
            case warningMessageEn = "warning_message_en"
            case warningMessageHi = "warning_message_hi"
            case interventionType = "intervention_type"
        }
    }

    public struct FlaggedEntity: Codable {
        public let entityType: String
        public let value: String
        public let confidenceScore: Double

        enum CodingKeys: String, CodingKey {
            case entityType = "entity_type"
            case value
            case confidenceScore = "confidence_score"
        }
    }

    public struct ScanMessageRequest: Codable {
        public let text: String
        public var language: String?
        public var source: String?

        public init(text: String, language: String? = nil, source: String? = nil) {
            self.text = text
            self.language = language
            self.source = source
        }
    }

    public struct ScanMessageResponse: Codable {
        public let result: ScanResult
        public let userMessageEn: String
        public let userMessageHi: String

        enum CodingKeys: String, CodingKey {
            case result
            case userMessageEn = "user_message_en"
            case userMessageHi = "user_message_hi"
        }
    }

    public struct ScanResult: Codable {
        public let isScam: Bool
        public let confidence: Double
        public let scamType: String
        public let riskLevel: String
        public let riskScore: Int
        public let recommendation: String
        public let processingTimeMs: Int

        enum CodingKeys: String, CodingKey {
            case isScam = "is_scam"
            case confidence
            case scamType = "scam_type"
            case riskLevel = "risk_level"
            case riskScore = "risk_score"
            case recommendation
            case processingTimeMs = "processing_time_ms"
        }
    }

    public struct Verdict: Codable {
        public let sessionId: String
        public let isScam: Bool
        public let scamType: String
        public let riskScore: Double
        public let riskLevel: String
        public let confidence: Double
        public let recommendedAction: String
        public let entities: [FlaggedEntity]
        public let modality: String
        public let attributions: [ShapAttribution]
        public let modelTier: String
        public let createdAt: String

        enum CodingKeys: String, CodingKey {
            case sessionId = "session_id"
            case isScam = "is_scam"
            case scamType = "scam_type"
            case riskScore = "risk_score"
            case riskLevel = "risk_level"
            case confidence
            case recommendedAction = "recommended_action"
            case entities
            case modality
            case attributions
            case modelTier = "model_tier"
            case createdAt = "created_at"
        }
    }

    public struct ShapAttribution: Codable {
        public let feature: String
        public let value: Double
        public let shapValue: Double
        public let direction: String

        enum CodingKeys: String, CodingKey {
            case feature
            case value
            case shapValue = "shap_value"
            case direction
        }
    }

    public struct ImageAnalysisResponse: Codable {
        public let result: ImageAnalysisResult
        public let processingTimeMs: Int
        public let verdict: Verdict?

        enum CodingKeys: String, CodingKey {
            case result
            case processingTimeMs = "processing_time_ms"
            case verdict
        }
    }

    public struct ImageAnalysisResult: Codable {
        public let hasQrCode: Bool
        public let qrCodes: [QRCodeResult]
        public let hasSuspiciousContent: Bool
        public let imageHash: String
        public let analysisNotes: [String]
        public let riskLevel: String

        enum CodingKeys: String, CodingKey {
            case hasQrCode = "has_qr_code"
            case qrCodes = "qr_codes"
            case hasSuspiciousContent = "has_suspicious_content"
            case imageHash = "image_hash"
            case analysisNotes = "analysis_notes"
            case riskLevel = "risk_level"
        }
    }

    public struct QRCodeResult: Codable {
        public let content: String
        public let contentType: String
        public let isSuspicious: Bool
        public let riskReasons: [String]

        enum CodingKeys: String, CodingKey {
            case content
            case contentType = "content_type"
            case isSuspicious = "is_suspicious"
            case riskReasons = "risk_reasons"
        }
    }

    public struct VoiceAnalysisRequest: Codable {
        public let transcript: String
        public var callerId: String?
        public var callDurationSeconds: Int?
        public var isIncoming: Bool?

        enum CodingKeys: String, CodingKey {
            case transcript
            case callerId = "caller_id"
            case callDurationSeconds = "call_duration_seconds"
            case isIncoming = "is_incoming"
        }
    }

    public struct VoiceAnalysisResponse: Codable {
        public let isScam: Bool
        public let confidence: Double
        public let scamType: String
        public let riskScore: Int
        public let riskLevel: String
        public let flaggedEntities: [FlaggedEntity]
        public let warningEn: String?
        public let warningHi: String?
        public let processingTimeMs: Int
        public let verdict: Verdict?

        enum CodingKeys: String, CodingKey {
            case isScam = "is_scam"
            case confidence
            case scamType = "scam_type"
            case riskScore = "risk_score"
            case riskLevel = "risk_level"
            case flaggedEntities = "flagged_entities"
            case warningEn = "warning_en"
            case warningHi = "warning_hi"
            case processingTimeMs = "processing_time_ms"
            case verdict
        }
    }

    public struct TrustShieldError: Error, LocalizedError {
        public let statusCode: Int
        public let detail: String

        public var errorDescription: String? {
            "TrustShield API error \(statusCode): \(detail)"
        }
    }

    // MARK: - Offline Queue

    private struct PendingRequest: Codable {
        let endpoint: String
        let method: String
        let body: Data?
        let queuedAt: TimeInterval
    }

    // MARK: - Properties

    private let config: Config
    private let session: URLSession
    private let offlineQueueKey = "com.trustshield.offline_queue"

    // MARK: - Init

    public init(config: Config = Config()) {
        self.config = config
        let sessionConfig = URLSessionConfiguration.default
        sessionConfig.timeoutIntervalForRequest = config.timeout
        self.session = URLSession(configuration: sessionConfig)
    }

    public convenience init(apiKey: String, baseUrl: String = "http://localhost:8000") {
        self.init(config: Config(baseUrl: baseUrl, apiKey: apiKey))
    }

    // MARK: - API Methods

    public func analyzeChat(_ request: AnalyzeRequest) async throws -> AnalyzeResponse {
        return try await requestWithRetry(endpoint: "/api/v1/analyze", method: "POST", body: request)
    }

    public func scanMessage(_ text: String, language: String? = nil) async throws -> ScanMessageResponse {
        let body = ScanMessageRequest(text: text, language: language)
        return try await requestWithRetry(endpoint: "/api/v1/scan-message", method: "POST", body: body)
    }

    public func healthCheck() async throws -> [String: String] {
        return try await requestNoBody(endpoint: "/health", method: "GET")
    }

    public func analyzeImage(imageData: Data, fileName: String = "image.jpg") async throws -> ImageAnalysisResponse {
        let url = URL(string: "\(config.baseUrl)/api/v1/analyze-image")!
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        if !config.apiKey.isEmpty {
            urlRequest.setValue(config.apiKey, forHTTPHeaderField: "X-API-Key")
        }

        let boundary = "Boundary-\(UUID().uuidString)"
        urlRequest.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(fileName)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: application/octet-stream\r\n\r\n".data(using: .utf8)!)
        body.append(imageData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        urlRequest.httpBody = body

        let (data, response) = try await session.data(for: urlRequest)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw TrustShieldError(statusCode: -1, detail: "Invalid response")
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            let errorBody = try? JSONDecoder().decode([String: String].self, from: data)
            throw TrustShieldError(
                statusCode: httpResponse.statusCode,
                detail: errorBody?["detail"] ?? "Unknown error"
            )
        }

        return try JSONDecoder().decode(ImageAnalysisResponse.self, from: data)
    }

    public func analyzeVoice(
        transcript: String,
        callerId: String? = nil,
        callDurationSeconds: Int? = nil,
        isIncoming: Bool = true
    ) async throws -> VoiceAnalysisResponse {
        let body = VoiceAnalysisRequest(
            transcript: transcript,
            callerId: callerId,
            callDurationSeconds: callDurationSeconds,
            isIncoming: isIncoming
        )
        return try await requestWithRetry(endpoint: "/api/v1/voice/analyze", method: "POST", body: body)
    }

    // MARK: - Offline Queue

    public func enqueueOfflineRequest(endpoint: String, method: String, body: Data? = nil) {
        var queue = loadOfflineQueue()
        let pending = PendingRequest(
            endpoint: endpoint,
            method: method,
            body: body,
            queuedAt: Date().timeIntervalSince1970
        )
        queue.append(pending)
        saveOfflineQueue(queue)
    }

    public func flushOfflineQueue() async {
        var queue = loadOfflineQueue()
        var remaining: [PendingRequest] = []

        for pending in queue {
            do {
                let url = URL(string: "\(config.baseUrl)\(pending.endpoint)")!
                var urlRequest = URLRequest(url: url)
                urlRequest.httpMethod = pending.method
                urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
                if !config.apiKey.isEmpty {
                    urlRequest.setValue(config.apiKey, forHTTPHeaderField: "X-API-Key")
                }
                urlRequest.httpBody = pending.body

                let (_, response) = try await session.data(for: urlRequest)
                if let httpResponse = response as? HTTPURLResponse,
                   (200...299).contains(httpResponse.statusCode) {
                    continue
                }
                remaining.append(pending)
            } catch {
                remaining.append(pending)
            }
        }

        saveOfflineQueue(remaining)
    }

    private func loadOfflineQueue() -> [PendingRequest] {
        guard let data = UserDefaults.standard.data(forKey: offlineQueueKey),
              let queue = try? JSONDecoder().decode([PendingRequest].self, from: data) else {
            return []
        }
        return queue
    }

    private func saveOfflineQueue(_ queue: [PendingRequest]) {
        if let data = try? JSONEncoder().encode(queue) {
            UserDefaults.standard.set(data, forKey: offlineQueueKey)
        }
    }

    // MARK: - Private

    private func requestWithRetry<T: Codable, B: Codable>(endpoint: String, method: String, body: B) async throws -> T {
        var lastError: Error?
        let maxAttempts = config.maxRetries + 1

        for attempt in 1...maxAttempts {
            do {
                return try await request(endpoint: endpoint, method: method, body: body)
            } catch {
                lastError = error
                if attempt < maxAttempts {
                    let backoffSeconds = min(pow(2.0, Double(attempt - 1)), 10.0)
                    try await Task.sleep(nanoseconds: UInt64(backoffSeconds * 1_000_000_000))
                }
            }
        }

        throw lastError ?? TrustShieldError(statusCode: -1, detail: "Request failed after retries")
    }

    private func request<T: Codable, B: Codable>(endpoint: String, method: String, body: B) async throws -> T {
        let url = URL(string: "\(config.baseUrl)\(endpoint)")!
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = method
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !config.apiKey.isEmpty {
            urlRequest.setValue(config.apiKey, forHTTPHeaderField: "X-API-Key")
        }
        urlRequest.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await session.data(for: urlRequest)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw TrustShieldError(statusCode: -1, detail: "Invalid response")
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            let errorBody = try? JSONDecoder().decode([String: String].self, from: data)
            throw TrustShieldError(
                statusCode: httpResponse.statusCode,
                detail: errorBody?["detail"] ?? "Unknown error"
            )
        }

        return try JSONDecoder().decode(T.self, from: data)
    }

    private func requestNoBody<T: Codable>(endpoint: String, method: String) async throws -> T {
        let url = URL(string: "\(config.baseUrl)\(endpoint)")!
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = method

        let (data, response) = try await session.data(for: urlRequest)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw TrustShieldError(statusCode: -1, detail: "Request failed")
        }

        return try JSONDecoder().decode(T.self, from: data)
    }
}
