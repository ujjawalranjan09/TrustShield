/**
 * TrustShield Web SDK
 *
 * TypeScript client library for integrating TrustShield fraud detection
 * into web-based payment platforms. Provides methods for:
 * - Real-time chat/session analysis
 * - Single message scanning (WhatsApp/Telegram bot integration)
 * - Entity reporting and lookup
 * - Pre-transaction webhook checks
 * - Image and voice analysis
 *
 * @example
 * ```ts
 * import { TrustShield } from '@trustshield/web-sdk';
 *
 * const ts = new TrustShield({ apiKey: 'your-api-key' });
 *
 * // Scan a single message
 * const result = await ts.scanMessage('Please share your OTP');
 * console.log(result.risk_level); // 'HIGH'
 *
 * // Analyze a full chat session
 * const analysis = await ts.analyzeChat({
 *   messages: [{ sender: 'agent', text: 'Share your OTP batao' }],
 *   session_metadata: { ... }
 * });
 * ```
 */

export const SDK_VERSION = '1.1.0';

export interface TrustShieldConfig {
  baseUrl?: string;
  apiKey?: string;
  timeout?: number;
  /** Maximum retries for transient failures (default: 3) */
  maxRetries?: number;
}

export interface ChatMessage {
  sender: string;
  text: string;
}

export interface SessionMetadata {
  client_app_id: string;
  session_id: string;
  contact_initiated_by: string;
  is_during_active_upi_session: boolean;
  user_device_hash: string;
  prior_reports_for_sender?: number;
}

export interface AnalyzeRequest {
  messages: ChatMessage[];
  session_metadata: SessionMetadata;
}

export interface FlaggedEntity {
  entity_type: string;
  value: string;
  confidence_score: number;
}

export interface Verdict {
  session_id: string;
  is_scam: boolean;
  scam_type: string;
  risk_score: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  confidence: number;
  recommended_action: string;
  entities: FlaggedEntity[];
  modality: 'TEXT' | 'VOICE' | 'IMAGE';
  attributions: Array<{
    feature: string;
    value: number;
    shap_value: number;
    direction: string;
  }>;
  model_tier: string;
  created_at: string;
}

export interface AnalyzeResponse {
  session_id: string;
  risk_score: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  recommended_action: string;
  flagged_entities: FlaggedEntity[];
  warning_message_en: string | null;
  warning_message_hi: string | null;
  intervention_type: string;
}

export interface ScanMessageRequest {
  text: string;
  language?: string;
  source?: string;
}

export interface ScanMessageResponse {
  result: {
    is_scam: boolean;
    confidence: number;
    scam_type: string;
    risk_level: string;
    risk_score: number;
    flagged_entities: FlaggedEntity[];
    warning_message_en: string | null;
    warning_message_hi: string | null;
    recommendation: string;
    processing_time_ms: number;
  };
  user_message_en: string;
  user_message_hi: string;
}

export interface ReportRequest {
  entity_value: string;
  entity_type: 'PHONE' | 'UPI' | 'URL' | 'EMAIL';
  scam_type: string;
  description?: string;
}

export interface ReportResponse {
  report_id: string;
  status: string;
  message: string;
}

export interface LookupResponse {
  entity_value: string;
  entity_type: string;
  is_flagged: boolean;
  report_count: number;
  risk_level: string;
}

export interface WebhookRequest {
  payer_vpa: string;
  payee_vpa: string;
  amount: number;
  device_fingerprint?: string;
}

export interface WebhookResponse {
  decision: string;
  reason: string;
  risk_score: number;
  risk_level: string;
}

export interface ImageAnalysisResponse {
  result: {
    has_qr_code: boolean;
    qr_codes: Array<{
      content: string;
      content_type: string;
      is_suspicious: boolean;
      risk_reasons: string[];
    }>;
    has_suspicious_content: boolean;
    image_hash: string;
    analysis_notes: string[];
    risk_level: string;
  };
  processing_time_ms: number;
  verdict: Verdict | null;
}

export interface VoiceAnalysisResponse {
  is_scam: boolean;
  confidence: number;
  scam_type: string;
  risk_score: number;
  risk_level: string;
  flagged_entities: FlaggedEntity[];
  warning_en: string | null;
  warning_hi: string | null;
  processing_time_ms: number;
  verdict: Verdict | null;
}

export class TrustShieldError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public detail: string
  ) {
    super(message);
    this.name = 'TrustShieldError';
  }
}

const REDACTED = '[REDACTED]';

function redactForLog(value: string): string {
  if (!value) return REDACTED;
  if (value.length <= 4) return REDACTED;
  return `${value[0]}***${value[value.length - 1]}`;
}

export class TrustShield {
  private baseUrl: string;
  private apiKey: string;
  private timeout: number;
  private maxRetries: number;

  constructor(config: TrustShieldConfig = {}) {
    this.baseUrl = (config.baseUrl || 'http://localhost:8000').replace(/\/$/, '');
    this.apiKey = config.apiKey || '';
    this.timeout = config.timeout || 5000;
    this.maxRetries = config.maxRetries ?? 3;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    let lastError: Error | undefined;
    const maxAttempts = this.maxRetries + 1;

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.timeout);

      try {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
          ...(this.apiKey ? { 'X-API-Key': this.apiKey } : {}),
          ...(options.headers as Record<string, string> || {}),
        };

        const response = await fetch(`${this.baseUrl}${endpoint}`, {
          ...options,
          headers,
          signal: controller.signal,
        });

        if (!response.ok) {
          const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
          const err = new TrustShieldError(
            `API error: ${response.status}`,
            response.status,
            error.detail || 'Unknown error'
          );
          if (response.status >= 500 && attempt < maxAttempts) {
            lastError = err;
            const backoffMs = Math.min(1000 * Math.pow(2, attempt - 1), 10000);
            await this.sleep(backoffMs);
            continue;
          }
          throw err;
        }

        return response.json();
      } catch (err) {
        if (err instanceof TrustShieldError) throw err;
        lastError = err as Error;
        if (attempt < maxAttempts) {
          const backoffMs = Math.min(1000 * Math.pow(2, attempt - 1), 10000);
          await this.sleep(backoffMs);
          continue;
        }
      } finally {
        clearTimeout(timeoutId);
      }
    }

    throw lastError || new TrustShieldError('Request failed after retries', 0, 'Max retries exceeded');
  }

  async analyzeChat(request: AnalyzeRequest): Promise<AnalyzeResponse> {
    return this.request<AnalyzeResponse>('/api/v1/analyze', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async scanMessage(text: string, options?: { language?: string; source?: string }): Promise<ScanMessageResponse> {
    return this.request<ScanMessageResponse>('/api/v1/scan-message', {
      method: 'POST',
      body: JSON.stringify({ text, ...options }),
    });
  }

  async reportEntity(request: ReportRequest): Promise<ReportResponse> {
    return this.request<ReportResponse>('/api/v1/report', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async lookupEntity(entityType: string, entityValue: string): Promise<LookupResponse> {
    return this.request<LookupResponse>(
      `/api/v1/lookup/${entityType}/${encodeURIComponent(entityValue)}`
    );
  }

  async checkTransaction(request: WebhookRequest): Promise<WebhookResponse> {
    return this.request<WebhookResponse>('/api/v1/webhook/pre-transaction', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async analyzeImage(imageData: Blob | File): Promise<ImageAnalysisResponse> {
    const formData = new FormData();
    formData.append('file', imageData);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const headers: Record<string, string> = {};
      if (this.apiKey) {
        headers['X-API-Key'] = this.apiKey;
      }

      const response = await fetch(`${this.baseUrl}/api/v1/analyze-image`, {
        method: 'POST',
        headers,
        body: formData,
        signal: controller.signal,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new TrustShieldError(
          `API error: ${response.status}`,
          response.status,
          error.detail || 'Unknown error'
        );
      }

      return response.json();
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async analyzeVoice(transcript: string, options?: {
    caller_id?: string;
    call_duration_seconds?: number;
    is_incoming?: boolean;
  }): Promise<VoiceAnalysisResponse> {
    return this.request<VoiceAnalysisResponse>('/api/v1/voice/analyze', {
      method: 'POST',
      body: JSON.stringify({ transcript, ...options }),
    });
  }

  async healthCheck(): Promise<{ status: string }> {
    return this.request<{ status: string }>('/health');
  }
}

export default TrustShield;
