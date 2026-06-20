import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { TrustShield, TrustShieldError } from '../src'

describe('TrustShield SDK', () => {
  let sdk: TrustShield
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    sdk = new TrustShield({ apiKey: 'test-key', baseUrl: 'http://localhost:8000', maxRetries: 2, timeout: 1000 })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    globalThis.fetch = originalFetch
  })

  describe('constructor', () => {
    it('uses default config values', () => {
      const defaultSdk = new TrustShield()
      expect(defaultSdk).toBeDefined()
    })

    it('strips trailing slash from baseUrl', async () => {
      const s = new TrustShield({ apiKey: 'k', baseUrl: 'http://example.com/' })
      const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ status: 'ok' }) })
      globalThis.fetch = mockFetch
      await s.healthCheck()
      expect(mockFetch).toHaveBeenCalledWith(
        'http://example.com/health',
        expect.any(Object)
      )
    })
  })

  describe('analyzeChat', () => {
    it('returns AnalyzeResponse on success', async () => {
      const mockResponse = {
        session_id: 'sess-1',
        risk_score: 85,
        risk_level: 'HIGH',
        recommended_action: 'HARD_BLOCK',
        flagged_entities: [],
        warning_message_en: 'Warning!',
        warning_message_hi: null,
        intervention_type: 'PUSH_ALERT'
      }
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      })

      const result = await sdk.analyzeChat({
        messages: [{ sender: 'agent', text: 'Share your OTP' }],
        session_metadata: {
          client_app_id: 'app1',
          session_id: 'sess-1',
          contact_initiated_by: 'agent',
          is_during_active_upi_session: true,
          user_device_hash: 'hash1'
        }
      })

      expect(result.risk_level).toBe('HIGH')
      expect(result.risk_score).toBe(85)
      expect(result.session_id).toBe('sess-1')
    })

    it('sends correct headers with API key', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ session_id: 's', risk_score: 0, risk_level: 'LOW', recommended_action: 'NONE', flagged_entities: [], warning_message_en: null, warning_message_hi: null, intervention_type: 'NONE' })
      })

      await sdk.analyzeChat({
        messages: [{ sender: 'u', text: 'hi' }],
        session_metadata: { client_app_id: 'a', session_id: 's', contact_initiated_by: 'u', is_during_active_upi_session: false, user_device_hash: 'h' }
      })

      const [, init] = globalThis.fetch.mock.calls[0]
      expect(init.headers['X-API-Key']).toBe('test-key')
      expect(init.headers['Content-Type']).toBe('application/json')
    })
  })

  describe('scanMessage', () => {
    it('returns ScanMessageResponse', async () => {
      const mockResponse = {
        result: { is_scam: true, confidence: 0.95, scam_type: 'OTP_HARVESTING', risk_level: 'HIGH', risk_score: 90, flagged_entities: [], warning_message_en: 'Be careful', warning_message_hi: null, recommendation: 'BLOCK', processing_time_ms: 120 },
        user_message_en: 'Scam detected',
        user_message_hi: null
      }
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      })

      const result = await sdk.scanMessage('Share your OTP batao')
      expect(result.result.is_scam).toBe(true)
      expect(result.result.scam_type).toBe('OTP_HARVESTING')
    })

    it('passes language option in body', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ result: { is_scam: false, confidence: 0.1, scam_type: 'NONE', risk_level: 'LOW', risk_score: 5, flagged_entities: [], warning_message_en: null, warning_message_hi: null, recommendation: 'ALLOW', processing_time_ms: 50 }, user_message_en: 'Safe', user_message_hi: null })
      })

      await sdk.scanMessage('hello', { language: 'hi' })
      const [, init] = globalThis.fetch.mock.calls[0]
      const body = JSON.parse(init.body)
      expect(body.language).toBe('hi')
    })
  })

  describe('retry logic', () => {
    it('retries on 503 then succeeds', async () => {
      const mockFetch = vi.fn()
        .mockResolvedValueOnce({ ok: false, status: 503, json: () => Promise.resolve({ detail: 'Service unavailable' }) })
        .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ status: 'ok' }) })

      globalThis.fetch = mockFetch

      const result = await sdk.healthCheck()
      expect(result.status).toBe('ok')
      expect(mockFetch).toHaveBeenCalledTimes(2)
    })

    it('exhausts retries and throws TrustShieldError', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false, status: 503, json: () => Promise.resolve({ detail: 'Down' })
      })
      globalThis.fetch = mockFetch

      await expect(sdk.healthCheck()).rejects.toThrow(TrustShieldError)
      expect(mockFetch).toHaveBeenCalledTimes(3)
    })

    it('retries on network error then succeeds', async () => {
      const mockFetch = vi.fn()
        .mockRejectedValueOnce(new TypeError('fetch failed'))
        .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ status: 'ok' }) })

      globalThis.fetch = mockFetch

      const result = await sdk.healthCheck()
      expect(result.status).toBe('ok')
      expect(mockFetch).toHaveBeenCalledTimes(2)
    })

    it('retries on network error then exhausts', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Network error'))

      await expect(sdk.healthCheck()).rejects.toThrow()
    })
  })

  describe('error handling', () => {
    it('throws TrustShieldError on 4xx', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Unauthorized' })
      })

      await expect(sdk.healthCheck()).rejects.toThrow(TrustShieldError)
    })

    it('includes status code in error', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: 'Not found' })
      })

      try {
        await sdk.healthCheck()
        expect.fail('should have thrown')
      } catch (e) {
        expect(e).toBeInstanceOf(TrustShieldError)
        expect((e as TrustShieldError).statusCode).toBe(404)
        expect((e as TrustShieldError).detail).toBe('Not found')
      }
    })
  })

  describe('reportEntity', () => {
    it('returns ReportResponse', async () => {
      const mockResponse = { report_id: 'rpt-1', status: 'submitted', message: 'Reported' }
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      })

      const result = await sdk.reportEntity({ entity_value: '9999999999', entity_type: 'PHONE', scam_type: 'OTP_HARVESTING' })
      expect(result.report_id).toBe('rpt-1')
      expect(result.status).toBe('submitted')
    })
  })

  describe('lookupEntity', () => {
    it('builds correct URL with encoded value', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ entity_value: 'test@upi', entity_type: 'UPI', is_flagged: false, report_count: 0, risk_level: 'LOW' })
      })

      await sdk.lookupEntity('UPI', 'test@upi')
      expect(globalThis.fetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/lookup/UPI/test%40upi',
        expect.any(Object)
      )
    })
  })

  describe('checkTransaction', () => {
    it('returns WebhookResponse', async () => {
      const mockResponse = { decision: 'ALLOW', reason: 'Low risk', risk_score: 10, risk_level: 'LOW' }
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      })

      const result = await sdk.checkTransaction({ payer_vpa: 'user@bank', payee_vpa: 'merchant@bank', amount: 500 })
      expect(result.decision).toBe('ALLOW')
      expect(result.risk_score).toBe(10)
    })
  })

  describe('healthCheck', () => {
    it('returns status', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ status: 'healthy' })
      })

      const result = await sdk.healthCheck()
      expect(result.status).toBe('healthy')
    })
  })

  describe('analyzeVoice', () => {
    it('returns VoiceAnalysisResponse', async () => {
      const mockResponse = {
        is_scam: true,
        confidence: 0.92,
        scam_type: 'CALL_FORWARDING',
        risk_score: 88,
        risk_level: 'HIGH',
        flagged_entities: [{ entity_type: 'PHONE', value: '99999', confidence_score: 0.8 }],
        warning_en: 'Warning!',
        warning_hi: null,
        processing_time_ms: 200,
        verdict: null
      }
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      })

      const result = await sdk.analyzeVoice('Send me your OTP', { caller_id: '12345' })
      expect(result.is_scam).toBe(true)
      expect(result.risk_level).toBe('HIGH')
    })
  })
})
