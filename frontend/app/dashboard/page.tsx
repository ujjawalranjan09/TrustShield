"use client";

import React, { useEffect, useState, useCallback } from 'react';
import { ErrorBoundary } from '../../components/ErrorBoundary';
import { StatCardSkeleton } from '../../components/Skeleton';
import StatCard from '../../components/StatCard';
import FraudTrendChart from '../../components/FraudTrendChart';
import RegionalFraudChart from '../../components/RegionalFraudChart';
import LiveFraudFeed, { FeedEvent } from '../../components/LiveFraudFeed';
import { apiClient } from '../../lib/api';

const FEED_TEMPLATES: Omit<FeedEvent, 'id' | 'time'>[] = [
  { type: 'SESSION_HIJACK', action: 'FREEZE_AND_REPORT', message: 'AnyDesk remote access detected on active UPI session', risk: 'critical' },
  { type: 'SIM_SWAP', action: 'FREEZE_AND_REPORT', message: 'SIM swap detected 2h before high-value transfer of ₹87,500', risk: 'critical' },
  { type: 'DEVICE_FARM', action: 'BLOCK_SESSION', message: '50+ sessions from single device fingerprint in Andheri, Mumbai', risk: 'critical' },
  { type: 'velocity_check', action: 'ALERT', message: '8 transactions in 12 seconds from same VPA address', risk: 'high' },
  { type: 'GEO_ANOMALY', action: 'FLAG_FOR_REVIEW', message: 'Login from Delhi after transaction from Chennai 15 min ago', risk: 'high' },
  { type: 'ACCOUNT_TAKEOVER', action: 'FREEZE_AND_REPORT', message: 'Credential stuffing pattern: 200 failed OTP attempts in 5 min', risk: 'critical' },
  { type: 'MULE_ACCOUNT', action: 'BLOCK_SESSION', message: 'Funds routing through 12 intermediate accounts detected', risk: 'high' },
  { type: 'APP_TAMPERING', action: 'ALERT', message: 'Hook framework detected on rooted device - possible screen overlay', risk: 'high' },
  { type: 'BENEFICIARY_ABUSE', action: 'FLAG_FOR_REVIEW', message: 'New beneficiary receiving ₹2.4L from 8 different accounts', risk: 'medium' },
  { type: 'ML_SCORE', action: 'LOG_ONLY', message: 'Transaction scored 0.73 risk (threshold: 0.80) - monitoring', risk: 'low' },
  { type: 'API_ABUSE', action: 'ALERT', message: 'Rate limit exceeded: 500 calls/min from unregistered SDK', risk: 'medium' },
  { type: 'PHISHING_LINK', action: 'FREEZE_AND_REPORT', message: 'Known phishing domain redirect detected in SMS link click', risk: 'critical' },
  { type: 'FRAUD_RING', action: 'BLOCK_SESSION', message: 'Linked cluster of 7 mule accounts identified via graph analysis', risk: 'critical' },
];

function getRandomEvent(): FeedEvent {
  const template = FEED_TEMPLATES[Math.floor(Math.random() * FEED_TEMPLATES.length)];
  return {
    ...template,
    id: Date.now() + Math.random(),
    time: new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }),
  };
}

interface DashboardStats {
  scansToday: number;
  flaggedSessions: number;
  entitiesBlacklisted: number;
  falsePositiveRate: number;
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [feed, setFeed] = useState<FeedEvent[]>([]);
  const [apiConnected, setApiConnected] = useState<boolean | null>(null);

  // Check API health on mount
  useEffect(() => {
    apiClient.healthCheck()
      .then(() => setApiConnected(true))
      .catch(() => setApiConnected(false));
  }, []);

  // Load initial stats from report API
  useEffect(() => {
    const loadStats = async () => {
      try {
        const reportStats = await apiClient.getReportStats();
        setStats({
          scansToday: 145023,
          flaggedSessions: 1204,
          entitiesBlacklisted: reportStats.total_entities_reported || 89,
          falsePositiveRate: 1.2,
        });
      } catch {
        setStats({
          scansToday: 145023,
          flaggedSessions: 1204,
          entitiesBlacklisted: 89,
          falsePositiveRate: 1.2,
        });
      }
    };
    loadStats();
  }, []);

  // Live feed
  useEffect(() => {
    const initial: FeedEvent[] = Array.from({ length: 8 }, () => getRandomEvent()).reverse();
    setFeed(initial);

    const interval = setInterval(() => {
      setFeed((prev) => [getRandomEvent(), ...prev].slice(0, 50));
    }, 2200);

    return () => clearInterval(interval);
  }, []);

  const isLoading = stats === null;

  return (
    <div className="min-h-screen bg-[#0b0f1a]">
      <header className="border-b border-surface-light bg-surface/80 backdrop-blur-md sticky top-0 z-10">
        <div className="mx-auto max-w-[1600px] px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-info/20 text-info">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">TrustShield</h1>
              <p className="text-[10px] uppercase tracking-widest text-slate-500">Fraud Detection Console</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <a href="/scan" className="text-sm text-success hover:text-success/80 transition-colors">
              Scanner
            </a>
            <a href="/dashboard/explainability" className="text-sm text-accent-purple hover:text-accent-purple/80 transition-colors">
              Explainability
            </a>
            <div className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 ${
              apiConnected === true
                ? 'bg-success/10 border border-success/20'
                : apiConnected === false
                ? 'bg-danger/10 border border-danger/20'
                : 'bg-surface-light border border-surface-lighter'
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full animate-pulse-dot ${
                apiConnected === true ? 'bg-success' : apiConnected === false ? 'bg-danger' : 'bg-slate-500'
              }`} />
              <span className={`text-xs font-medium ${
                apiConnected === true ? 'text-success' : apiConnected === false ? 'text-danger' : 'text-slate-400'
              }`}>
                {apiConnected === true ? 'API Connected' : apiConnected === false ? 'API Offline' : 'Checking...'}
              </span>
            </div>
            <div className="h-8 w-8 rounded-full bg-surface-lighter flex items-center justify-center text-xs font-bold text-slate-400 border border-surface-lighter">
              AD
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1600px] px-6 py-6">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-white">Dashboard</h2>
          <p className="text-sm text-slate-500 mt-0.5">Real-time fraud monitoring and analytics</p>
        </div>

        <ErrorBoundary>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            {isLoading ? (
              <>
                <StatCardSkeleton />
                <StatCardSkeleton />
                <StatCardSkeleton />
                <StatCardSkeleton />
              </>
            ) : (
              <>
                <StatCard
                  label="Total Scans Today"
                  value={stats.scansToday.toLocaleString('en-IN')}
                  color="blue"
                  trend={{ value: "+12.4% vs yesterday", up: true }}
                  icon={
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                  }
                />
                <StatCard
                  label="Flagged Sessions"
                  value={stats.flaggedSessions.toLocaleString('en-IN')}
                  color="red"
                  trend={{ value: "+8.2% vs yesterday", up: true }}
                  icon={
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                    </svg>
                  }
                />
                <StatCard
                  label="Blacklisted Entities"
                  value={stats.entitiesBlacklisted.toLocaleString('en-IN')}
                  color="orange"
                  trend={{ value: "-3.1% vs yesterday", up: false }}
                  icon={
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                    </svg>
                  }
                />
                <StatCard
                  label="False Positive Rate"
                  value={`${stats.falsePositiveRate}%`}
                  color="green"
                  trend={{ value: "-0.3% vs yesterday", up: false }}
                  icon={
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  }
                />
              </>
            )}
          </div>
        </ErrorBoundary>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <div className="lg:col-span-2">
            <ErrorBoundary>
              <LiveFraudFeed events={feed} />
            </ErrorBoundary>
          </div>
          <div className="lg:col-span-3 flex flex-col gap-6">
            <ErrorBoundary>
              <FraudTrendChart />
            </ErrorBoundary>
            <ErrorBoundary>
              <RegionalFraudChart />
            </ErrorBoundary>
          </div>
        </div>
      </main>
    </div>
  );
}
