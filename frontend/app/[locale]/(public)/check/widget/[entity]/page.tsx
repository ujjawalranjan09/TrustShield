'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { Shield, AlertTriangle } from 'lucide-react';

interface ReputationData {
  entity: string;
  reputation_tier: string;
  score: number;
  report_count_bucket: string;
}

const TIER_STYLES: Record<string, { bg: string; text: string; border: string; label: string }> = {
  confirmed_scam: {
    bg: 'bg-red-500/10',
    text: 'text-red-400',
    border: 'border-red-500/30',
    label: 'Confirmed Scam',
  },
  suspicious: {
    bg: 'bg-orange-500/10',
    text: 'text-orange-400',
    border: 'border-orange-500/30',
    label: 'Suspicious',
  },
  watch: {
    bg: 'bg-yellow-500/10',
    text: 'text-yellow-400',
    border: 'border-yellow-500/30',
    label: 'Watch List',
  },
  clean: {
    bg: 'bg-green-500/10',
    text: 'text-green-400',
    border: 'border-green-500/30',
    label: 'No Reports',
  },
};

const COUNT_LABELS: Record<string, string> = {
  none: 'No reports filed',
  few: '1-2 reports',
  several: '3-10 reports',
  many: '10+ reports',
};

export default function TrustBadgePage({ params }: { params: { entity: string } }) {
  const [data, setData] = useState<ReputationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const entity = decodeURIComponent(params.entity);

  const fetchReputation = useCallback(async () => {
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${baseUrl}/api/v1/reputation/${encodeURIComponent(entity)}/public`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load reputation');
    } finally {
      setLoading(false);
    }
  }, [entity]);

  useEffect(() => {
    fetchReputation();
  }, [fetchReputation]);

  if (loading) {
    return (
      <div className="min-h-[120px] flex items-center justify-center bg-[#0b0f1a] rounded-xl border border-surface-light">
        <div className="animate-pulse text-slate-500 text-sm">Checking...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-[120px] flex items-center gap-2 p-4 bg-[#0b0f1a] rounded-xl border border-red-500/20">
        <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
        <span className="text-sm text-red-400">{error}</span>
      </div>
    );
  }

  if (!data) return null;

  const tier = TIER_STYLES[data.reputation_tier] || TIER_STYLES.clean;
  const isClean = data.reputation_tier === 'clean';

  return (
    <div className={`min-h-[120px] p-4 bg-[#0b0f1a] rounded-xl border ${tier.border}`}>
      <div className="flex items-center gap-3">
        <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${tier.bg}`}>
          <Shield className={`h-4 w-4 ${tier.text}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white truncate">{data.entity}</span>
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium ${tier.bg} ${tier.text} border ${tier.border}`}>
              {tier.label}
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            {COUNT_LABELS[data.report_count_bucket] || 'Unknown'}
          </p>
        </div>
      </div>

      {isClean && (
        <div className="mt-3 pt-3 border-t border-surface-light">
          <p className="text-xs text-slate-400">
            No reports yet — be the first to report.
          </p>
          <a
            href="/report"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block mt-1.5 text-xs font-medium text-info hover:underline"
          >
            Report this entity →
          </a>
        </div>
      )}
    </div>
  );
}
