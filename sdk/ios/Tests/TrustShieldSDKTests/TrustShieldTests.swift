import XCTest
@testable import TrustShieldSDK

final class TrustShieldTests: XCTestCase {

    // MARK: - Verdict Decoding

    func testVerdictDecodes() throws {
        let json = """
        {
            "session_id": "sess-1",
            "is_scam": true,
            "scam_type": "OTP_HARVESTING",
            "risk_score": 85.0,
            "risk_level": "HIGH",
            "confidence": 0.92,
            "recommended_action": "HARD_BLOCK",
            "entities": [
                {"entity_type": "PHONE", "value": "9999999999", "confidence_score": 0.85}
            ],
            "modality": "TEXT",
            "attributions": [
                {"feature": "otp_keyword", "value": 1.0, "shap_value": 0.45, "direction": "positive"}
            ],
            "model_tier": "ensemble_v2",
            "created_at": "2025-01-15T10:00:00Z"
        }
        """
        let data = json.data(using: .utf8)!
        let verdict = try JSONDecoder().decode(TrustShield.Verdict.self, from: data)

        XCTAssertTrue(verdict.isScam)
        XCTAssertEqual(verdict.riskScore, 85.0)
        XCTAssertEqual(verdict.riskLevel, "HIGH")
        XCTAssertEqual(verdict.scamType, "OTP_HARVESTING")
        XCTAssertEqual(verdict.sessionId, "sess-1")
        XCTAssertEqual(verdict.entities.count, 1)
        XCTAssertEqual(verdict.entities.first?.entityType, "PHONE")
        XCTAssertEqual(verdict.attributions.first?.feature, "otp_keyword")
        XCTAssertEqual(verdict.modelTier, "ensemble_v2")
    }

    func testVerdictDecodesWithEmptyEntities() throws {
        let json = """
        {
            "session_id": "sess-2",
            "is_scam": false,
            "scam_type": "NONE",
            "risk_score": 5.0,
            "risk_level": "LOW",
            "confidence": 0.1,
            "recommended_action": "NONE",
            "entities": [],
            "modality": "TEXT",
            "attributions": [],
            "model_tier": "ensemble_v2",
            "created_at": "2025-01-15T10:00:00Z"
        }
        """
        let data = json.data(using: .utf8)!
        let verdict = try JSONDecoder().decode(TrustShield.Verdict.self, from: data)

        XCTAssertFalse(verdict.isScam)
        XCTAssertEqual(verdict.riskLevel, "LOW")
        XCTAssertTrue(verdict.entities.isEmpty)
    }

    // MARK: - ChatMessage

    func testChatMessageEncodes() throws {
        let message = TrustShield.ChatMessage(sender: "agent", text: "Share your OTP")
        let data = try JSONEncoder().encode(message)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: String]

        XCTAssertEqual(dict["sender"], "agent")
        XCTAssertEqual(dict["text"], "Share your OTP")
    }

    func testChatMessageDecodes() throws {
        let json = "{\"sender\":\"user\",\"text\":\"hello\"}"
        let data = json.data(using: .utf8)!
        let message = try JSONDecoder().decode(TrustShield.ChatMessage.self, from: data)

        XCTAssertEqual(message.sender, "user")
        XCTAssertEqual(message.text, "hello")
    }

    // MARK: - SessionMetadata

    func testSessionMetadataCodingKeys() throws {
        let metadata = TrustShield.SessionMetadata(
            clientAppId: "app-1",
            sessionId: "sess-1",
            contactInitiatedBy: "user",
            isDuringActiveUpiSession: true,
            userDeviceHash: "hash-abc"
        )
        let data = try JSONEncoder().encode(metadata)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: Any]

        XCTAssertEqual(dict["client_app_id"] as? String, "app-1")
        XCTAssertEqual(dict["session_id"] as? String, "sess-1")
        XCTAssertEqual(dict["contact_initiated_by"] as? String, "user")
        XCTAssertEqual(dict["is_during_active_upi_session"] as? Bool, true)
        XCTAssertEqual(dict["user_device_hash"] as? String, "hash-abc")
    }

    // MARK: - ScanMessageResponse

    func testScanMessageResponseDecodes() throws {
        let json = """
        {
            "result": {
                "is_scam": true,
                "confidence": 0.95,
                "scam_type": "OTP_HARVESTING",
                "risk_level": "HIGH",
                "risk_score": 90,
                "recommendation": "BLOCK",
                "processing_time_ms": 120
            },
            "user_message_en": "Scam detected",
            "user_message_hi": "धोखा पाया गया"
        }
        """
        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(TrustShield.ScanMessageResponse.self, from: data)

        XCTAssertTrue(response.result.isScam)
        XCTAssertEqual(response.result.scamType, "OTP_HARVESTING")
        XCTAssertEqual(response.result.riskScore, 90)
        XCTAssertEqual(response.userMessageEn, "Scam detected")
    }

    // MARK: - FlaggedEntity

    func testFlaggedEntityDecodes() throws {
        let json = """
        {
            "entity_type": "PHONE",
            "value": "9999999999",
            "confidence_score": 0.85
        }
        """
        let data = json.data(using: .utf8)!
        let entity = try JSONDecoder().decode(TrustShield.FlaggedEntity.self, from: data)

        XCTAssertEqual(entity.entityType, "PHONE")
        XCTAssertEqual(entity.value, "9999999999")
        XCTAssertEqual(entity.confidenceScore, 0.85, accuracy: 0.001)
    }

    // MARK: - Config

    func testConfigDefaults() {
        let config = TrustShield.Config()
        XCTAssertEqual(config.baseUrl, "http://localhost:8000")
        XCTAssertEqual(config.apiKey, "")
        XCTAssertEqual(config.timeout, 5.0)
        XCTAssertEqual(config.maxRetries, 3)
    }

    func testConfigCustomValues() {
        let config = TrustShield.Config(
            baseUrl: "https://api.example.com",
            apiKey: "my-key",
            timeout: 10.0,
            maxRetries: 5
        )
        XCTAssertEqual(config.baseUrl, "https://api.example.com")
        XCTAssertEqual(config.apiKey, "my-key")
        XCTAssertEqual(config.timeout, 10.0)
        XCTAssertEqual(config.maxRetries, 5)
    }

    // MARK: - TrustShield Initialization

    func testTrustShieldInitWithApiKey() {
        let ts = TrustShield(apiKey: "test-key")
        XCTAssertNotNil(ts)
    }

    func testTrustShieldInitWithConfig() {
        let config = TrustShield.Config(apiKey: "key", baseUrl: "https://api.test.com")
        let ts = TrustShield(config: config)
        XCTAssertNotNil(ts)
    }

    func testSDKVersion() {
        XCTAssertEqual(TrustShield.sdkVersion, "1.1.0")
    }

    // MARK: - AnalyzeResponse

    func testAnalyzeResponseDecodes() throws {
        let json = """
        {
            "session_id": "sess-1",
            "risk_score": 85,
            "risk_level": "HIGH",
            "recommended_action": "HARD_BLOCK",
            "flagged_entities": [],
            "warning_message_en": "Warning!",
            "warning_message_hi": null,
            "intervention_type": "PUSH_ALERT"
        }
        """
        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(TrustShield.AnalyzeResponse.self, from: data)

        XCTAssertEqual(response.sessionId, "sess-1")
        XCTAssertEqual(response.riskScore, 85)
        XCTAssertEqual(response.riskLevel, "HIGH")
        XCTAssertEqual(response.recommendedAction, "HARD_BLOCK")
        XCTAssertEqual(response.interventionType, "PUSH_ALERT")
        XCTAssertNil(response.warningMessageHi)
    }

    // MARK: - Offline Queue

    func testEnqueueOfflineRequest() {
        let ts = TrustShield(apiKey: "key")
        ts.enqueueOfflineRequest(endpoint: "/api/v1/scan", method: "POST", body: Data())
        // Verify no crash — the queue is persisted to UserDefaults
    }

    // MARK: - VoiceAnalysisResponse

    func testVoiceAnalysisResponseDecodes() throws {
        let json = """
        {
            "is_scam": true,
            "confidence": 0.9,
            "scam_type": "CALL_FORWARDING",
            "risk_score": 88,
            "risk_level": "HIGH",
            "flagged_entities": [],
            "warning_en": "Warning!",
            "warning_hi": null,
            "processing_time_ms": 200,
            "verdict": null
        }
        """
        let data = json.data(using: .utf8)!
        let response = try JSONDecoder().decode(TrustShield.VoiceAnalysisResponse.self, from: data)

        XCTAssertTrue(response.isScam)
        XCTAssertEqual(response.riskLevel, "HIGH")
        XCTAssertEqual(response.processingTimeMs, 200)
        XCTAssertNil(response.verdict)
    }

    // MARK: - ShapAttribution

    func testShapAttributionDecodes() throws {
        let json = """
        {
            "feature": "otp_keyword",
            "value": 1.0,
            "shap_value": 0.45,
            "direction": "positive"
        }
        """
        let data = json.data(using: .utf8)!
        let attr = try JSONDecoder().decode(TrustShield.ShapAttribution.self, from: data)

        XCTAssertEqual(attr.feature, "otp_keyword")
        XCTAssertEqual(attr.value, 1.0)
        XCTAssertEqual(attr.shapValue, 0.45)
        XCTAssertEqual(attr.direction, "positive")
    }

    // MARK: - TrustShieldError

    func testTrustShieldErrorDescription() {
        let error = TrustShieldError(statusCode: 401, detail: "Unauthorized")
        XCTAssertEqual(error.statusCode, 401)
        XCTAssertEqual(error.detail, "Unauthorized")
        XCTAssertEqual(error.errorDescription, "TrustShield API error 401: Unauthorized")
    }
}
