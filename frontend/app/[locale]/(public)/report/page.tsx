'use client';

import React, { useState } from 'react';
import { apiClient, ReportRequest } from '@/lib/api';
import { Shield, CheckCircle, AlertTriangle } from 'lucide-react';

const SCAM_TYPES = [
  { value: 'OTP_HARVESTING', label: 'OTP Harvesting' },
  { value: 'VISHING', label: 'Vishing (Voice Phishing)' },
  { value: 'REMOTE_ACCESS', label: 'Remote Access Scam' },
  { value: 'REFUND_SCAM', label: 'Refund Scam' },
  { value: 'FAKE_SUPPORT', label: 'Fake Customer Support' },
  { value: 'PHISHING', label: 'Phishing' },
  { value: 'SIM_SWAP', label: 'SIM Swap' },
];

const ENTITY_TYPES = [
  { value: 'PHONE', label: 'Phone Number' },
  { value: 'UPI', label: 'UPI ID' },
  { value: 'URL', label: 'URL' },
];

export default function ReportPage() {
  const [entityValue, setEntityValue] = useState('');
  const [entityType, setEntityType] = useState<ReportRequest['entity_type']>('PHONE');
  const [scamType, setScamType] = useState(SCAM_TYPES[0].value);
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{ reportId: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!entityValue.trim()) return;

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await apiClient.reportEntity({
        entity_value: entityValue.trim(),
        entity_type: entityType,
        scam_type: scamType,
        description: description.trim() || undefined,
      });
      setSuccess({ reportId: response.report_id });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to submit report';
      if (message.includes('429') || message.toLowerCase().includes('rate limit')) {
        setError('Too many reports. Please wait a moment and try again.');
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleReportAnother = () => {
    setEntityValue('');
    setEntityType('PHONE');
    setScamType(SCAM_TYPES[0].value);
    setDescription('');
    setSuccess(null);
    setError(null);
  };

  const getPlaceholder = () => {
    switch (entityType) {
      case 'PHONE': return '+91 98765 43210';
      case 'UPI': return 'user@paytm';
      case 'URL': return 'https://suspicious-site.com';
      default: return '';
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-[#0b0f1a]">
        <header className="border-b border-surface-light bg-surface/80 backdrop-blur-md sticky top-0 z-10">
          <div className="mx-auto max-w-4xl px-6 py-4 flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/20 text-primary">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">TrustShield</h1>
              <p className="text-[10px] uppercase tracking-widest text-slate-500">Report a Scam</p>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-4xl px-6 py-16">
          <div className="bg-surface rounded-xl p-8 border border-surface-light text-center max-w-md mx-auto">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-green-500/10 mx-auto mb-4">
              <CheckCircle className="h-8 w-8 text-green-400" />
            </div>
            <h2 className="text-xl font-bold text-white mb-2">Report Submitted</h2>
            <p className="text-sm text-slate-400 mb-6">
              Thank you for helping protect the community.
            </p>
            <div className="bg-surface-light rounded-lg p-4 mb-6">
              <p className="text-xs text-slate-400 mb-1">Reference Number</p>
              <p className="text-lg font-mono font-bold text-white">{success.reportId}</p>
            </div>
            <button
              onClick={handleReportAnother}
              className="w-full px-6 py-2.5 bg-info text-white rounded-lg hover:bg-info/90 transition-colors font-medium"
            >
              Report Another
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0b0f1a]">
      <header className="border-b border-surface-light bg-surface/80 backdrop-blur-md sticky top-0 z-10">
        <div className="mx-auto max-w-4xl px-6 py-4 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/20 text-primary">
            <Shield className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">TrustShield</h1>
            <p className="text-[10px] uppercase tracking-widest text-slate-500">Report a Scam</p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-white">Report Fraudulent Activity</h2>
          <p className="text-sm text-slate-400 mt-1">
            Help protect others by reporting scam phone numbers, UPI IDs, or URLs
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-surface rounded-xl p-6 border border-surface-light space-y-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Entity Type
              </label>
              <select
                value={entityType}
                onChange={(e) => setEntityType(e.target.value as ReportRequest['entity_type'])}
                className="w-full px-4 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-info/50"
              >
                {ENTITY_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Value
              </label>
              <input
                type="text"
                value={entityValue}
                onChange={(e) => setEntityValue(e.target.value)}
                placeholder={getPlaceholder()}
                className="w-full px-4 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-info/50"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Scam Type
            </label>
            <select
              value={scamType}
              onChange={(e) => setScamType(e.target.value)}
              className="w-full px-4 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-info/50"
            >
              {SCAM_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Description <span className="text-slate-500">(optional)</span>
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe what happened..."
              rows={3}
              className="w-full px-4 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-info/50 resize-none"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-red-400/10 border border-red-400/20">
              <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !entityValue.trim()}
            className="w-full px-6 py-2.5 bg-info text-white rounded-lg hover:bg-info/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Submitting...' : 'Submit Report'}
          </button>
        </form>
      </main>
    </div>
  );
}
