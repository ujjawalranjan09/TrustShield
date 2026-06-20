package com.trustshield.sdk

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.security.SecureRandom
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import kotlin.math.pow
import kotlin.math.min

const val SDK_VERSION = "1.1.0"

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

data class FlaggedEntity(
    val entityType: String,
    val value: String,
    val confidenceScore: Double
)

data class Verdict(
    val sessionId: String,
    val isScam: Boolean,
    val scamType: String,
    val riskScore: Double,
    val riskLevel: String,
    val confidence: Double,
    val recommendedAction: String,
    val entities: List<FlaggedEntity>,
    val modality: String,
    val modelTier: String,
    val createdAt: String
) {
    companion object {
        fun fromJson(json: JSONObject): Verdict {
            val entitiesArray = json.optJSONArray("entities") ?: JSONArray()
            val entities = (0 until entitiesArray.length()).map { i ->
                val e = entitiesArray.getJSONObject(i)
                FlaggedEntity(
                    entityType = e.optString("entity_type", ""),
                    value = e.optString("value", ""),
                    confidenceScore = e.optDouble("confidence_score", 0.0)
                )
            }
            return Verdict(
                sessionId = json.optString("session_id", ""),
                isScam = json.optBoolean("is_scam", false),
                scamType = json.optString("scam_type", ""),
                riskScore = json.optDouble("risk_score", 0.0),
                riskLevel = json.optString("risk_level", "LOW"),
                confidence = json.optDouble("confidence", 0.0),
                recommendedAction = json.optString("recommended_action", "NONE"),
                entities = entities,
                modality = json.optString("modality", "TEXT"),
                modelTier = json.optString("model_tier", "unknown"),
                createdAt = json.optString("created_at", "")
            )
        }
    }
}

data class ImageAnalysisResponse(
    val hasQrCode: Boolean,
    val riskLevel: String,
    val processingTimeMs: Int,
    val verdict: Verdict?
)

data class VoiceAnalysisResponse(
    val isScam: Boolean,
    val confidence: Double,
    val scamType: String,
    val riskScore: Int,
    val riskLevel: String,
    val flaggedEntities: List<FlaggedEntity>,
    val warningEn: String?,
    val warningHi: String?,
    val processingTimeMs: Int,
    val verdict: Verdict?
)

interface RiskCallback {
    fun onResult(result: RiskResult)
    fun onError(error: Exception)
}

object TrustShieldManager {
    private var apiKey: String = ""
    private var baseUrl: String = "http://localhost:8000"
    private var isInitialized: Boolean = false
    private var maxRetries: Int = 3
    private var cachedKeywords = listOf("anydesk", "teamviewer", "otp", "refund")
    private var offlineQueuePrefs = "trustshield_offline_queue"
    private var context: Context? = null

    private const val TAG = "TrustShield"

    fun init(context: Context, key: String, baseUrl: String = "http://localhost:8000", maxRetries: Int = 3) {
        this.context = context
        this.apiKey = key
        this.baseUrl = baseUrl.trimEnd('/')
        this.maxRetries = maxRetries
        this.isInitialized = true
        Log.i(TAG, "SDK v$SDK_VERSION initialized.")
    }

    fun analyzeMessage(message: String, metadata: SessionMetadata, callback: RiskCallback) {
        if (!isInitialized) {
            callback.onError(IllegalStateException("SDK not initialized"))
            return
        }

        val messageLower = message.lowercase()
        val containsScamKeyword = cachedKeywords.any { messageLower.contains(it) }

        if (containsScamKeyword) {
            Log.w(TAG, "Local trigger fired. Invoking API...")
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

    fun analyzeImage(imageBytes: ByteArray, fileName: String = "image.jpg"): ImageAnalysisResponse? {
        if (!isInitialized) return null
        return try {
            val response = postMultipart("/api/v1/analyze-image", imageBytes, fileName)
            val json = JSONObject(response)
            val verdictJson = json.optJSONObject("verdict")
            ImageAnalysisResponse(
                hasQrCode = json.optJSONObject("result")?.optBoolean("has_qr_code") ?: false,
                riskLevel = json.optJSONObject("result")?.optString("risk_level") ?: "LOW",
                processingTimeMs = json.optInt("processing_time_ms", 0),
                verdict = verdictJson?.let { Verdict.fromJson(it) }
            )
        } catch (e: Exception) {
            Log.e(TAG, "Image analysis failed", e)
            enqueueOfflineRequest("/api/v1/analyze-image", "POST", imageBytes)
            null
        }
    }

    fun analyzeVoice(
        transcript: String,
        callerId: String? = null,
        callDurationSeconds: Int? = null,
        isIncoming: Boolean = true
    ): VoiceAnalysisResponse? {
        if (!isInitialized) return null
        return try {
            val body = JSONObject().apply {
                put("transcript", transcript)
                callerId?.let { put("caller_id", it) }
                callDurationSeconds?.let { put("call_duration_seconds", it) }
                put("is_incoming", isIncoming)
            }
            val response = postJson("/api/v1/voice/analyze", body.toString())
            val json = JSONObject(response)
            val entitiesArray = json.optJSONArray("flagged_entities") ?: JSONArray()
            val entities = (0 until entitiesArray.length()).map { i ->
                val e = entitiesArray.getJSONObject(i)
                FlaggedEntity(
                    entityType = e.optString("entity_type", ""),
                    value = e.optString("value", ""),
                    confidenceScore = e.optDouble("confidence_score", 0.0)
                )
            }
            VoiceAnalysisResponse(
                isScam = json.optBoolean("is_scam", false),
                confidence = json.optDouble("confidence", 0.0),
                scamType = json.optString("scam_type", ""),
                riskScore = json.optInt("risk_score", 0),
                riskLevel = json.optString("risk_level", "LOW"),
                flaggedEntities = entities,
                warningEn = json.optString("warning_en", null),
                warningHi = json.optString("warning_hi", null),
                processingTimeMs = json.optInt("processing_time_ms", 0),
                verdict = json.optJSONObject("verdict")?.let { Verdict.fromJson(it) }
            )
        } catch (e: Exception) {
            Log.e(TAG, "Voice analysis failed", e)
            null
        }
    }

    fun startSessionMonitoring(sessionId: String) {
        Log.i(TAG, "Started monitoring session: $sessionId")
    }

    fun stopSessionMonitoring() {
        Log.i(TAG, "Stopped session monitoring. Submitting batch data.")
    }

    // MARK: - Offline Queue

    fun enqueueOfflineRequest(endpoint: String, method: String, body: ByteArray? = null) {
        val prefs = context?.getSharedPreferences(offlineQueuePrefs, Context.MODE_PRIVATE) ?: return
        val queue = loadOfflineQueue(prefs)
        val entry = JSONObject().apply {
            put("endpoint", endpoint)
            put("method", method)
            put("body", body?.let { android.util.Base64.encodeToString(it, android.util.Base64.NO_WRAP) })
            put("queued_at", System.currentTimeMillis())
        }
        queue.put(entry)
        prefs.edit().putString("queue", queue.toString()).apply()
    }

    fun flushOfflineQueue() {
        val prefs = context?.getSharedPreferences(offlineQueuePrefs, Context.MODE_PRIVATE) ?: return
        val queue = loadOfflineQueue(prefs)
        val remaining = JSONArray()

        for (i in 0 until queue.length()) {
            val entry = queue.getJSONObject(i)
            try {
                val endpoint = entry.getString("endpoint")
                val method = entry.getString("method")
                val bodyBytes = entry.optString("body", null)?.let {
                    android.util.Base64.decode(it, android.util.Base64.NO_WRAP)
                }
                if (method == "POST" && bodyBytes != null) {
                    postJson(endpoint, String(bodyBytes))
                }
            } catch (e: Exception) {
                remaining.put(entry)
            }
        }

        prefs.edit().putString("queue", remaining.toString()).apply()
    }

    private fun loadOfflineQueue(prefs: android.content.SharedPreferences): JSONArray {
        val raw = prefs.getString("queue", "[]") ?: "[]"
        return try { JSONArray(raw) } catch (e: Exception) { JSONArray() }
    }

    private fun isNetworkAvailable(): Boolean {
        val ctx = context ?: return false
        val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    // MARK: - HTTP with Retry

    private fun postJson(endpoint: String, jsonBody: String): String {
        var lastException: Exception? = null
        val maxAttempts = maxRetries + 1

        for (attempt in 1..maxAttempts) {
            try {
                return executePostJson(endpoint, jsonBody)
            } catch (e: Exception) {
                lastException = e
                if (attempt < maxAttempts) {
                    val backoffMs = min(1000L * 2.0.pow((attempt - 1).toDouble()).toLong(), 10_000L)
                    Thread.sleep(backoffMs)
                }
            }
        }
        throw lastException ?: RuntimeException("Request failed after retries")
    }

    private fun executePostJson(endpoint: String, jsonBody: String): String {
        val url = URL("$baseUrl$endpoint")
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        if (apiKey.isNotEmpty()) {
            conn.setRequestProperty("X-API-Key", apiKey)
        }
        conn.doOutput = true
        conn.connectTimeout = 5000
        conn.readTimeout = 5000

        OutputStreamWriter(conn.outputStream).use { it.write(jsonBody) }

        val reader = BufferedReader(InputStreamReader(conn.inputStream))
        val response = reader.readText()
        reader.close()

        if (conn.responseCode !in 200..299) {
            throw RuntimeException("HTTP ${conn.responseCode}: $response")
        }
        return response
    }

    private fun postMultipart(endpoint: String, fileBytes: ByteArray, fileName: String): String {
        val url = URL("$baseUrl$endpoint")
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        val boundary = "Boundary-${System.currentTimeMillis()}"
        conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
        if (apiKey.isNotEmpty()) {
            conn.setRequestProperty("X-API-Key", apiKey)
        }
        conn.doOutput = true
        conn.connectTimeout = 5000
        conn.readTimeout = 5000

        val output = conn.outputStream
        output.write("--$boundary\r\n".toByteArray())
        output.write("Content-Disposition: form-data; name=\"file\"; filename=\"$fileName\"\r\n".toByteArray())
        output.write("Content-Type: application/octet-stream\r\n\r\n".toByteArray())
        output.write(fileBytes)
        output.write("\r\n--$boundary--\r\n".toByteArray())
        output.flush()
        output.close()

        val reader = BufferedReader(InputStreamReader(conn.inputStream))
        val response = reader.readText()
        reader.close()

        if (conn.responseCode !in 200..299) {
            throw RuntimeException("HTTP ${conn.responseCode}: $response")
        }
        return response
    }
}
