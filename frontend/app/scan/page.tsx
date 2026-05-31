'use client';

import React, { useState } from 'react';
import { ErrorBoundary } from '../../components/ErrorBoundary';
import { apiClient } from '../../lib/api';

interface ScanResult {
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
}

interface ScanResponse {
  result: ScanResult;
  user_message_en: string;
  user_message_hi: string;
}

const SAMPLE_MESSAGES = [
  { label: 'OTP Scam (Hindi)', text: 'Hello sir, I am calling from bank. aapka debit card block ho gaya hai. Please share your OTP verify karne ke liye.' },
  { label: 'AnyDesk Scam', text: 'Aapko refund process karne ke liye ek baar screen share karo. AnyDesk app download kijiye aur code bataiye: 123456789.' },
  { label: 'QR Code Scam', text: 'Sir, your refund of Rs 5000 is approved. Please scan this QR code. Payment receive karne ke liye PIN enter karein.' },
  { label: 'Legitimate Message', text: 'Hi, when will my order be delivered? Your order will be delivered by tomorrow 8 PM.' },
];

export default function ScanPage() {
  const [message, setMessage] = useState('');
  const [result, setResult] = useState<ScanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleScan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/scan-message`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(process.env.NEXT_PUBLIC_API_KEY ? { 'X-API-Key': process.env.NEXT_PUBLIC_API_KEY } : {}),
          },
          body: JSON.stringify({ text: message }),
        }
      );

      if (!response.ok) {
        throw new Error('Failed to scan message');
      }

      const data: ScanResponse = await response.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to scan message');
    } finally {
      setLoading(false);
    }
  };

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'CRITICAL': return 'text-red-400 bg-red-400/10 border-red-400/30';
      case 'HIGH': return 'text-orange-400 bg-orange-400/10 border-orange-400/30';
      case 'MEDIUM': return 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30';
      default: return 'text-green-400 bg-green-400/10 border-green-400/30';
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 70) return 'text-red-400';
    if (score >= 40) return 'text-orange-400';
    if (score >= 20) return 'text-yellow-400';
    return 'text-green-400';
  };

  return (
    <div className="min-h-screen bg-[#0b0f1a]">
      <header className="border-b border-surface-light bg-surface/80 backdrop-blur-md sticky top-0 z-10">
        <div className="mx-auto max-w-4xl px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-success/20 text-success">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">TrustShield</h1>
              <p className="text-[10px] uppercase tracking-widest text-slate-500">Scam Scanner</p>
            </div>
          </div>
          <a href="/dashboard" className="text-sm text-info hover:text-info/80 transition-colors">
            Dashboard
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-white">WhatsApp / Telegram Scam Scanner</h2>
          <p className="text-sm text-slate-400 mt-1">
            Forward a suspicious message and get an instant risk assessment
          </p>
        </div>

        <ErrorBoundary>
          <form onSubmit={handleScan} className="bg-surface rounded-xl p-6 border border-surface-light mb-8">
            <div className="mb-4">
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Paste or type the suspicious message
              </label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Paste the suspicious message here... (e.g., 'Hello sir, I am calling from bank. Please share your OTP.')"
                rows={5}
                className="w-full px-4 py-3 bg-surface-light border border-surface-lighter rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-info/50 resize-none"
              />
            </div>

            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={loading || !message.trim()}
                className="px-6 py-2.5 bg-info text-white rounded-lg hover:bg-info/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Scanning...' : 'Scan Message'}
              </button>
              <span className="text-xs text-slate-500">
                Powered by TrustShield NLP Pipeline
              </span>
            </div>
          </form>
        </ErrorBoundary>

        <div className="mb-6">
          <p className="text-sm font-medium text-slate-400 mb-3">Try a sample message:</p>
          <div className="flex flex-wrap gap-2">
            {SAMPLE_MESSAGES.map((sample, i) => (
              <button
                key={i}
                onClick={() => setMessage(sample.text)}
                className="px-3 py-1.5 bg-surface-light border border-surface-lighter rounded-lg text-xs text-slate-300 hover:bg-surface-lighter transition-colors"
              >
                {sample.label}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="bg-red-400/10 border border-red-400/20 rounded-xl p-4 mb-8">
            <p className="text-red-400">{error}</p>
          </div>
        )}

        {result && (
          <div className="space-y-6">
            {/* Risk Score Card */}
            <div className={`rounded-xl border p-6 ${getRiskColor(result.result.risk_level)}`}>
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-lg font-semibold">
                    {result.result.is_scam ? 'Scam Detected' : 'Appears Safe'}
                  </h3>
                  <p className="text-sm opacity-80 mt-1">
                    Risk Level: {result.result.risk_level}
                  </p>
                </div>
                <div className="text-right">
                  <p className={`text-4xl font-bold ${getScoreColor(result.result.risk_score)}`}>
                    {result.result.risk_score}
                  </p>
                  <p className="text-xs opacity-60">/ 100</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="opacity-60">Confidence</p>
                  <p className="font-medium">{(result.result.confidence * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="opacity-60">Scam Type</p>
                  <p className="font-medium">{result.result.scam_type.replace('_', ' ')}</p>
                </div>
                <div>
                  <p className="opacity-60">Processing Time</p>
                  <p className="font-medium">{result.result.processing_time_ms}ms</p>
                </div>
              </div>
            </div>

            {/* Warning Messages */}
            {(result.result.warning_message_en || result.result.warning_message_hi) && (
              <div className="bg-surface rounded-xl p-5 border border-surface-light">
                <h4 className="text-sm font-semibold text-slate-300 mb-3">Warnings</h4>
                {result.result.warning_message_en && (
                  <p className="text-sm text-white mb-2">{result.result.warning_message_en}</p>
                )}
                {result.result.warning_message_hi && (
                  <p className="text-sm text-slate-400">{result.result.warning_message_hi}</p>
                )}
              </div>
            )}

            {/* Flagged Entities */}
            {result.result.flagged_entities.length > 0 && (
              <div className="bg-surface rounded-xl p-5 border border-surface-light">
                <h4 className="text-sm font-semibold text-slate-300 mb-3">Flagged Entities</h4>
                <div className="space-y-2">
                  {result.result.flagged_entities.map((entity, i) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-surface-light/50 rounded-lg">
                      <div>
                        <p className="text-sm font-medium text-white">{entity.value}</p>
                        <p className="text-xs text-slate-400">{entity.entity_type}</p>
                      </div>
                      <span className="text-xs text-slate-500">
                        {(entity.confidence_score * 100).toFixed(0)}% confidence
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recommendation */}
            <div className="bg-surface rounded-xl p-5 border border-surface-light">
              <h4 className="text-sm font-semibold text-slate-300 mb-3">Recommendation</h4>
              <p className="text-sm text-white">{result.result.recommendation}</p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
