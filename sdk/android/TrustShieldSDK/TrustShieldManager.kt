package com.trustshield.sdk

import android.content.Context
import android.util.Log

data class SessionMetadata(
    val clientAppId: String,
    val sessionId: String,
    val contactInitiatedBy: String,
    val isDuringActiveUpiSession: Boolean,
    val userDeviceHash: String
)

enum class RiskLevel { LOW, MEDIUM, HIGH, CRITICAL }
enum class ActionCode { NONE, SOFT_WARNING, HARD_BLOCK, FREEZE_AND_REPORT, CRITICAL_REPORT }

data class RiskResult(
    val riskLevel: RiskLevel,
    val action: ActionCode,
    val warningEn: String?,
    val warningHi: String?
)

interface RiskCallback {
    fun onResult(result: RiskResult)
    fun onError(error: Exception)
}

object TrustShieldManager {
    private var apiKey: String = ""
    private var isInitialized: Boolean = false
    private var cachedKeywords = listOf("anydesk", "teamviewer", "otp", "refund")

    fun init(context: Context, key: String) {
        this.apiKey = key
        this.isInitialized = true
        Log.i("TrustShield", "SDK Initialized.")
        // Pre-load offline keyword dictionary
    }

    fun analyzeMessage(message: String, metadata: SessionMetadata, callback: RiskCallback) {
        if (!isInitialized) {
            callback.onError(IllegalStateException("SDK not initialized"))
            return
        }

        // Lightweight local check
        val messageLower = message.lowercase()
        val containsScamKeyword = cachedKeywords.any { messageLower.contains(it) }

        if (containsScamKeyword) {
            // Mock API call to backend /v1/analyze
            // RetrofitClient.analyze(...)
            Log.w("TrustShield", "Local trigger fired. Invoking API...")

            // Mocking the result
            val result = RiskResult(
                riskLevel = RiskLevel.HIGH,
                action = ActionCode.HARD_BLOCK,
                warningEn = "Warning: High risk of fraud! We have disabled PIN entry temporarily.",
                warningHi = "Chetawani: Fraud ka khatra!"
            )
            callback.onResult(result)
        } else {
            callback.onResult(RiskResult(RiskLevel.LOW, ActionCode.NONE, null, null))
        }
    }

    fun startSessionMonitoring(sessionId: String) {
        Log.i("TrustShield", "Started monitoring session: $sessionId")
        // Start velocity tracking, keystroke dynamics, etc.
    }

    fun stopSessionMonitoring() {
        Log.i("TrustShield", "Stopped session monitoring. Submitting batch data.")
        // Batch API call
    }
}
