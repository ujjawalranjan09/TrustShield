"use client";

import React from 'react';

export interface FeedEvent {
  id: number;
  type: string;
  action: string;
  message: string;
  risk: 'critical' | 'high' | 'medium' | 'low';
  time: string;
}

interface LiveFraudFeedProps {
  events: FeedEvent[];
}

const riskStyles: Record<string, { dot: string; badge: string; label: string }> = {
  critical: { dot: 'bg-danger animate-pulse-dot', badge: 'bg-danger/20 text-danger border-danger/30', label: 'CRITICAL' },
  high: { dot: 'bg-warning', badge: 'bg-warning/20 text-warning border-warning/30', label: 'HIGH' },
  medium: { dot: 'bg-yellow-500', badge: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30', label: 'MEDIUM' },
  low: { dot: 'bg-info', badge: 'bg-info/20 text-info border-info/30', label: 'LOW' },
};

const actionColors: Record<string, string> = {
  FREEZE_AND_REPORT: 'text-danger',
  BLOCK_SESSION: 'text-danger',
  ALERT: 'text-warning',
  FLAG_FOR_REVIEW: 'text-yellow-400',
  LOG_ONLY: 'text-info',
  MONITOR: 'text-accent-purple',
};

export default function LiveFraudFeed({ events }: LiveFraudFeedProps) {
  return (
    <div className="rounded-xl border border-surface-light bg-surface shadow-lg overflow-hidden">
      <div className="flex items-center justify-between p-5 pb-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full rounded-full bg-danger opacity-75 animate-ping" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-danger" />
          </span>
          <h3 className="text-sm font-semibold text-slate-300">Live Fraud Feed</h3>
        </div>
        <span className="text-xs text-slate-500">{events.length} events</span>
      </div>
      <div className="h-[460px] overflow-y-auto scrollbar-thin px-5 pb-4">
        {events.map((event) => {
          const risk = riskStyles[event.risk];
          return (
            <div
              key={event.id}
              className="animate-feed-in mb-2.5 rounded-lg border border-surface-lighter bg-surface-light/50 px-4 py-3 transition-colors hover:bg-surface-light"
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${risk.dot}`} />
                  <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold ${risk.badge}`}>
                    {risk.label}
                  </span>
                </div>
                <span className="text-[10px] text-slate-500 font-mono">{event.time}</span>
              </div>
              <p className="text-sm text-slate-200 leading-snug">{event.message}</p>
              <div className="mt-1.5 flex items-center justify-between">
                <span className={`text-xs font-semibold ${actionColors[event.action] || 'text-slate-400'}`}>
                  {event.action}
                </span>
              </div>
            </div>
          );
        })}
        {events.length === 0 && (
          <div className="flex h-full items-center justify-center text-slate-500 text-sm">
            Waiting for events...
          </div>
        )}
      </div>
    </div>
  );
}
