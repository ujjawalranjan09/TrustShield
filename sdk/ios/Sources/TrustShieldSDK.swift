import Foundation

/// TrustShield iOS SDK
///
/// Provides fraud detection capabilities for iOS payment apps:
/// - Real-time message scanning
/// - Session monitoring
/// - Overlay/remote access detection
/// - Behavioral signal collection
///
/// Usage:
/// ```swift
/// let trustShield = TrustShield(apiKey: "your-key", baseUrl: "https://api.trustshield.io")
/// let result = await trustShield.scanMessage("Share your OTP batao")
/// print(result.riskLevel) // "HIGH"
/// ```
public class TrustShield {

    public struct Config {
        public var baseUrl: String
        public var apiKey: String
        public var timeout: TimeInterval

        public init(
            baseUrl: String = "http://localhost:8000",
            apiKey: String = "",
            timeout: TimeInterval = 5.0
        ) {
            self.baseUrl = baseUrl
            self.apiKey = apiKey
            self.timeout = timeout
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

    public struct TrustShieldError: Error, LocalizedError {
        public let statusCode: Int
        public let detail: String

        public var errorDescription: String? {
            "TrustShield API error \(statusCode): \(detail)"
        }
    }

    // MARK: - Properties

    private let config: Config
    private let session: URLSession

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

    /// Analyze a full chat session for fraud indicators
    public func analyzeChat(_ request: AnalyzeRequest) async throws -> AnalyzeResponse {
        return try await request(endpoint: "/api/v1/analyze", method: "POST", body: request)
    }

    /// Scan a single message for scam indicators (stateless)
    public func scanMessage(_ text: String, language: String? = nil) async throws -> ScanMessageResponse {
        let body = ScanMessageRequest(text: text, language: language)
        return try await request(endpoint: "/api/v1/scan-message", method: "POST", body: body)
    }

    /// Health check
    public func healthCheck() async throws -> [String: String] {
        return try await requestNoBody(endpoint: "/health", method: "GET")
    }

    // MARK: - Private

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
