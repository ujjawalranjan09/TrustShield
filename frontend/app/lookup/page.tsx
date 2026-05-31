'use client';

import React, { useState } from 'react';
import { apiClient, LookupResponse } from '../../lib/api';

export default function LookupPage() {
  const [entityType, setEntityType] = useState<string>('PHONE');
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
      setError(err instanceof Error ? err.message : 'Failed to lookup entity');
    } finally {
      setLoading(false);
    }
  };

  const getRiskColor = (riskLevel: string) => {
    switch (riskLevel) {
      case 'critical':
        return 'text-red-400 bg-red-400/10 border-red-400/20';
      case 'high':
        return 'text-orange-400 bg-orange-400/10 border-orange-400/20';
      case 'medium':
        return 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20';
      default:
        return 'text-green-400 bg-green-400/10 border-green-400/20';
    }
  };

  return (
    <div className="min-h-screen bg-[#0b0f1a]">
      <header className="border-b border-surface-light bg-surface/80 backdrop-blur-md sticky top-0 z-10">
        <div className="mx-auto max-w-4xl px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-info/20 text-info">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">TrustShield</h1>
              <p className="text-[10px] uppercase tracking-widest text-slate-500">Scammer Lookup</p>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-white">Community Scammer Database</h2>
          <p className="text-sm text-slate-400 mt-1">
            Check if a phone number, UPI ID, or URL has been reported as fraudulent
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
                <option value="PHONE">Phone Number</option>
                <option value="UPI">UPI ID</option>
                <option value="URL">URL</option>
                <option value="EMAIL">Email</option>
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
                placeholder={
                  entityType === 'PHONE'
                    ? '+91 98765 43210'
                    : entityType === 'UPI'
                    ? 'user@paytm'
                    : entityType === 'URL'
                    ? 'https://suspicious-site.com'
                    : 'scammer@email.com'
                }
                className="w-full px-4 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-info/50"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={loading || !entityValue.trim()}
            className="mt-4 px-6 py-2.5 bg-info text-white rounded-lg hover:bg-info/90 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Checking...' : 'Check Entity'}
          </button>
        </form>

        {error && (
          <div className="bg-red-400/10 border border-red-400/20 rounded-xl p-4 mb-8">
            <p className="text-red-400">{error}</p>
          </div>
        )}

        {result && (
          <div className="bg-surface rounded-xl p-6 border border-surface-light">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-white">{result.entity_value}</h3>
                <p className="text-sm text-slate-400">{result.entity_type}</p>
              </div>
              <span className={`px-3 py-1 rounded-full text-xs font-medium border ${getRiskColor(result.risk_level)}`}>
                {result.risk_level.toUpperCase()}
              </span>
            </div>
            
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <p className="text-sm text-slate-400">Status</p>
                <p className={`font-medium ${result.is_flagged ? 'text-red-400' : 'text-green-400'}`}>
                  {result.is_flagged ? 'FLAGGED' : 'CLEAR'}
                </p>
              </div>
              <div>
                <p className="text-sm text-slate-400">Reports</p>
                <p className="font-medium text-white">{result.report_count}</p>
              </div>
            </div>

            {result.first_reported && (
              <div className="text-sm text-slate-400">
                <p>First reported: {new Date(result.first_reported).toLocaleDateString()}</p>
                <p>Last seen: {result.last_seen ? new Date(result.last_seen).toLocaleDateString() : 'N/A'}</p>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
