/**
 * TrustShield Web SDK
 *
 * TypeScript client library for integrating TrustShield fraud detection
 * into web-based payment platforms. Provides methods for:
 * - Real-time chat/session analysis
 * - Single message scanning (WhatsApp/Telegram bot integration)
 * - Entity reporting and lookup
 * - Pre-transaction webhook checks
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

export interface TrustShieldConfig {
  /** API base URL (default: http://localhost:8000) */
  baseUrl?: string;
  /** API key for authentication */
  apiKey?: string;
  /** Request timeout in milliseconds (default: 5000) */
  timeout?: number;
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

export interface AnalyzeResponse {
  session_id: string;
  risk_score: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  recommended_action: string;
  flagged_entities: Array<{
    entity_type: string;
    value: string;
    confidence_score: number;
  }>;
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
    flagged_entities: Array<{
      entity_type: string;
      value: string;
      confidence_score: number;
    }>;
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

export class TrustShield {
  private baseUrl: string;
  private apiKey: string;
  private timeout: number;

  constructor(config: TrustShieldConfig = {}) {
    this.baseUrl = (config.baseUrl || 'http://localhost:8000').replace(/\/$/, '');
    this.apiKey = config.apiKey || '';
    this.timeout = config.timeout || 5000;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
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

  /** Analyze a full chat session for fraud indicators */
  async analyzeChat(request: AnalyzeRequest): Promise<AnalyzeResponse> {
    return this.request<AnalyzeResponse>('/api/v1/analyze', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /** Scan a single message for scam indicators (stateless) */
  async scanMessage(text: string, options?: { language?: string; source?: string }): Promise<ScanMessageResponse> {
    return this.request<ScanMessageResponse>('/api/v1/scan-message', {
      method: 'POST',
      body: JSON.stringify({ text, ...options }),
    });
  }

  /** Report a suspicious entity to the community database */
  async reportEntity(request: ReportRequest): Promise<ReportResponse> {
    return this.request<ReportResponse>('/api/v1/report', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /** Look up an entity in the community database */
  async lookupEntity(entityType: string, entityValue: string): Promise<LookupResponse> {
    return this.request<LookupResponse>(
      `/api/v1/lookup/${entityType}/${encodeURIComponent(entityValue)}`
    );
  }

  /** Check a transaction via the pre-transaction webhook */
  async checkTransaction(request: WebhookRequest): Promise<WebhookResponse> {
    return this.request<WebhookResponse>('/api/v1/webhook/pre-transaction', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /** Health check */
  async healthCheck(): Promise<{ status: string }> {
    return this.request<{ status: string }>('/health');
  }
}

export default TrustShield;
