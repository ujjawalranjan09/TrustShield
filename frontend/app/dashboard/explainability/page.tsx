"use client";

import React, { useEffect, useState } from 'react';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  AreaChart, Area,
} from 'recharts';
import { ErrorBoundary } from '../../../components/ErrorBoundary';
import { StatCardSkeleton, ChartSkeleton } from '../../../components/Skeleton';
import { apiClient, DashboardStats } from '../../../lib/api';

const RISK_COLORS = {
  low: '#22c55e',
  medium: '#eab308',
  high: '#f97316',
  critical: '#ef4444',
};

const SCAM_TYPE_COLORS = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6'];

function StatCard({ label, value, color, icon }: { label: string; value: string | number; color: string; icon: React.ReactNode }) {
  const colorClasses: Record<string, string> = {
    blue: 'bg-info-dim/40 border-info/30 text-info',
    red: 'bg-danger-dim/40 border-danger/30 text-danger',
    orange: 'bg-warning-dim/40 border-warning/30 text-warning',
    green: 'bg-success-dim/40 border-success/30 text-success',
  };
  return (
    <div className={`rounded-xl border ${colorClasses[color] || colorClasses.blue} p-5`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">{label}</p>
          <p className="text-2xl font-bold">{value}</p>
        </div>
        <div className="rounded-lg p-2">{icon}</div>
      </div>
    </div>
  );
}

function RiskPieChart({ data }: { data: DashboardStats['risk_distribution'] }) {
  const chartData = [
    { name: 'Low', value: data.low, color: RISK_COLORS.low },
    { name: 'Medium', value: data.medium, color: RISK_COLORS.medium },
    { name: 'High', value: data.high, color: RISK_COLORS.high },
    { name: 'Critical', value: data.critical, color: RISK_COLORS.critical },
  ].filter(d => d.value > 0);

  return (
    <div className="rounded-xl border border-surface-light bg-surface p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-4">Risk Distribution</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={90}
              paddingAngle={3}
              dataKey="value"
            >
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
              itemStyle={{ color: '#e2e8f0' }}
            />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function ScamTypeBarChart({ data }: { data: DashboardStats['scam_type_breakdown'] }) {
  return (
    <div className="rounded-xl border border-surface-light bg-surface p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-4">Scam Type Breakdown</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 100 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} />
            <YAxis
              type="category"
              dataKey="scam_type"
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              width={100}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
              itemStyle={{ color: '#e2e8f0' }}
            />
            <Bar dataKey="count" radius={[0, 4, 4, 0]}>
              {data.map((_, index) => (
                <Cell key={`cell-${index}`} fill={SCAM_TYPE_COLORS[index % SCAM_TYPE_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function TemporalTrendChart({ data }: { data: DashboardStats['temporal_trend'] }) {
  return (
    <div className="rounded-xl border border-surface-light bg-surface p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-4">7-Day Reporting Trend</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="gradientReports" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.4} />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gradientConfirmed" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#ef4444" stopOpacity={0.4} />
                <stop offset="100%" stopColor="#ef4444" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
              itemStyle={{ color: '#e2e8f0' }}
            />
            <Legend />
            <Area type="monotone" dataKey="reports" stroke="#3b82f6" strokeWidth={2} fill="url(#gradientReports)" name="Reports" />
            <Area type="monotone" dataKey="confirmed" stroke="#ef4444" strokeWidth={2} fill="url(#gradientConfirmed)" name="Confirmed" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function ContributingFactorsTable({ factors }: { factors: DashboardStats['contributing_factors'] }) {
  return (
    <div className="rounded-xl border border-surface-light bg-surface p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-4">Risk Scoring Factors</h3>
      <div className="space-y-3">
        {factors.map((f, i) => (
          <div key={i} className="flex items-start gap-3 p-3 bg-surface-light/50 rounded-lg">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-info/20 text-info text-sm font-bold shrink-0">
              {Math.round(f.weight * 100)}%
            </div>
            <div>
              <p className="text-sm font-medium text-white">{f.factor}</p>
              <p className="text-xs text-slate-400 mt-0.5">{f.description}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TopEntitiesTable({ entities }: { entities: DashboardStats['top_entities'] }) {
  const getRiskColor = (level: string) => {
    switch (level) {
      case 'critical': return 'text-red-400 bg-red-400/10';
      case 'high': return 'text-orange-400 bg-orange-400/10';
      case 'medium': return 'text-yellow-400 bg-yellow-400/10';
      default: return 'text-green-400 bg-green-400/10';
    }
  };

  return (
    <div className="rounded-xl border border-surface-light bg-surface p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-4">Top Flagged Entities</h3>
      {entities.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-8">No entities reported yet</p>
      ) : (
        <div className="space-y-2">
          {entities.map((e, i) => (
            <div key={i} className="flex items-center justify-between p-3 bg-surface-light/50 rounded-lg">
              <div className="flex items-center gap-3">
                <span className="text-xs text-slate-500 w-6">#{i + 1}</span>
                <div>
                  <p className="text-sm font-medium text-white">{e.entity_value}</p>
                  <p className="text-xs text-slate-400">{e.entity_type} · {e.scam_type || 'N/A'}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-white">{e.report_count} reports</span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${getRiskColor(e.risk_level)}`}>
                  {e.risk_level}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ExplainabilityPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadStats = async () => {
      try {
        const data = await apiClient.getDashboardStats();
        setStats(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    };
    loadStats();
  }, []);

  return (
    <div className="min-h-screen bg-[#0b0f1a]">
      <header className="border-b border-surface-light bg-surface/80 backdrop-blur-md sticky top-0 z-10">
        <div className="mx-auto max-w-[1600px] px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-purple/20 text-accent-purple">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight">TrustShield</h1>
              <p className="text-[10px] uppercase tracking-widest text-slate-500">Explainability Dashboard</p>
            </div>
          </div>
          <a href="/dashboard" className="text-sm text-info hover:text-info/80 transition-colors">
            ← Back to Dashboard
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-[1600px] px-6 py-6">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-white">Explainability</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Understand why decisions are made — risk factors, entity breakdowns, and trends
          </p>
        </div>

        {error && (
          <div className="bg-red-400/10 border border-red-400/20 rounded-xl p-4 mb-6">
            <p className="text-red-400">{error}</p>
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
          </div>
        ) : stats && (
          <>
            <ErrorBoundary>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <StatCard
                  label="Total Scans Today"
                  value={stats.total_scans_today.toLocaleString('en-IN')}
                  color="blue"
                  icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>}
                />
                <StatCard
                  label="Flagged Sessions"
                  value={stats.flagged_sessions.toLocaleString('en-IN')}
                  color="red"
                  icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg>}
                />
                <StatCard
                  label="Blacklisted Entities"
                  value={stats.entities_blacklisted.toLocaleString('en-IN')}
                  color="orange"
                  icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" /></svg>}
                />
                <StatCard
                  label="False Positive Rate"
                  value={`${stats.false_positive_rate}%`}
                  color="green"
                  icon={<svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                />
              </div>
            </ErrorBoundary>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
              <ErrorBoundary>
                <RiskPieChart data={stats.risk_distribution} />
              </ErrorBoundary>
              <ErrorBoundary>
                <ScamTypeBarChart data={stats.scam_type_breakdown} />
              </ErrorBoundary>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
              <ErrorBoundary>
                <TemporalTrendChart data={stats.temporal_trend} />
              </ErrorBoundary>
              <ErrorBoundary>
                <ContributingFactorsTable factors={stats.contributing_factors} />
              </ErrorBoundary>
            </div>

            <ErrorBoundary>
              <TopEntitiesTable entities={stats.top_entities} />
            </ErrorBoundary>
          </>
        )}
      </main>
    </div>
  );
}
