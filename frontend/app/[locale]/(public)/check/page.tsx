'use client';

import React, { useState } from 'react';
import { apiClient, LookupResponse } from '@/lib/api';
import { Shield, Search, AlertTriangle } from 'lucide-react';

const ENTITY_TYPES = [
  { value: 'PHONE', label: 'Phone Number' },
  { value: 'UPI', label: 'UPI ID' },
  { value: 'URL', label: 'URL' },
];

export default function CheckPage() {
  const [entityType, setEntityType] = useState('PHONE');
  const [entityValue, setEntityValue] = useState('');
  const [result, setResult] = useState<LookupResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!entityValue.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await apiClient.lookupEntity(entityType, entityValue.trim());
      setResult(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to check entity';
      if (message.includes('429') || message.toLowerCase().includes('rate limit')) {
        setError('Too many requests. Please wait a moment and try again.');
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  };

  const getRiskBadge = (riskLevel: string, isFlagged: boolean) => {
    if (!isFlagged) {
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-green-400/10 text-green-400 border border-green-400/20">
          <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
          Low Risk
        </span>
      );
    }
    switch (riskLevel?.toLowerCase()) {
      case 'critical':
      case 'high':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-red-400/10 text-red-400 border border-red-400/20">
            <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
            High Risk
          </span>
        );
      case 'medium':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-yellow-400/10 text-yellow-400 border border-yellow-400/20">
            <span className="h-1.5 w-1.5 rounded-full bg-yellow-400" />
            Medium Risk
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-red-400/10 text-red-400 border border-red-400/20">
            <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
            Flagged
          </span>
        );
    }
  };

  const getPlaceholder = () => {
    switch (entityType) {
      case 'PHONE': return '+91 98765 43210';
      case 'UPI': return 'user@paytm';
      case 'URL': return 'https://suspicious-site.com';
      default: return '';
    }
  };

  return (
    <div className="min-h-screen bg-[#0b0f1a]">
      <header className="border-b border-surface-light bg-surface/80 backdrop-blur-md sticky top-0 z-10">
        <div className="mx-auto max-w-4xl px-6 py-4 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-info/20 text-info">
            <Shield className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">TrustShield</h1>
            <p className="text-[10px] uppercase tracking-widest text-slate-500">Reputation Check</p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-white">Check Reputation</h2>
          <p className="text-sm text-slate-400 mt-1">
            Find out if a phone number, UPI ID, or URL has been reported by the community
          </p>
        </div>

        <form onSubmit={handleLookup} className="bg-surface rounded-xl p-6 border border-surface-light mb-8">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Entity Type
              </label>
              <select
                value={entityType}
                onChange={(e) => setEntityType(e.target.value)}
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
          <button
            type="submit"
            disabled={loading || !entityValue.trim()}
            className="mt-4 px-6 py-2.5 bg-info text-white rounded-lg hover:bg-info/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <Search className="h-4 w-4" />
            {loading ? 'Checking...' : 'Check Entity'}
          </button>
        </form>

        {error && (
          <div className="flex items-center gap-2 p-4 rounded-xl bg-red-400/10 border border-red-400/20 mb-8">
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {result && (
          <div className="bg-surface rounded-xl p-6 border border-surface-light">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-white">{result.entity_value}</h3>
                <p className="text-sm text-slate-400">{result.entity_type}</p>
              </div>
              {getRiskBadge(result.risk_level, result.is_flagged)}
            </div>

            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="bg-surface-light rounded-lg p-3">
                <p className="text-xs text-slate-400 mb-1">Status</p>
                <p className={`text-sm font-semibold ${result.is_flagged ? 'text-red-400' : 'text-green-400'}`}>
                  {result.is_flagged ? 'FLAGGED' : 'CLEAR'}
                </p>
              </div>
              <div className="bg-surface-light rounded-lg p-3">
                <p className="text-xs text-slate-400 mb-1">Community Reports</p>
                <p className="text-sm font-semibold text-white">{result.report_count}</p>
              </div>
            </div>

            {(result.first_reported || result.last_seen) && (
              <div className="border-t border-surface-light pt-4 mt-4">
                <p className="text-xs text-slate-400">Timeline</p>
                <div className="mt-2 space-y-1">
                  {result.first_reported && (
                    <p className="text-sm text-slate-300">
                      First reported: {new Date(result.first_reported).toLocaleDateString()}
                    </p>
                  )}
                  {result.last_seen && (
                    <p className="text-sm text-slate-300">
                      Last seen: {new Date(result.last_seen).toLocaleDateString()}
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
