"use client";

import React from 'react';

interface StatCardProps {
  label: string;
  value: string;
  icon: React.ReactNode;
  color: 'blue' | 'red' | 'orange' | 'green' | 'purple';
  trend?: { value: string; up: boolean };
}

const colorMap = {
  blue: { bg: 'bg-info-dim/40', border: 'border-info/30', text: 'text-info', glow: 'shadow-info/10' },
  red: { bg: 'bg-danger-dim/40', border: 'border-danger/30', text: 'text-danger', glow: 'shadow-danger/10' },
  orange: { bg: 'bg-warning-dim/40', border: 'border-warning/30', text: 'text-warning', glow: 'shadow-warning/10' },
  green: { bg: 'bg-success-dim/40', border: 'border-success/30', text: 'text-success', glow: 'shadow-success/10' },
  purple: { bg: 'bg-purple-900/40', border: 'border-accent-purple/30', text: 'text-accent-purple', glow: 'shadow-accent-purple/10' },
};

export default function StatCard({ label, value, icon, color, trend }: StatCardProps) {
  const c = colorMap[color];

  return (
    <div className={`relative overflow-hidden rounded-xl border ${c.border} ${c.bg} p-5 shadow-lg ${c.glow} transition-all duration-300 hover:scale-[1.02] hover:shadow-xl`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400 mb-1">{label}</p>
          <p className={`text-3xl font-bold ${c.text}`}>{value}</p>
          {trend && (
            <div className={`flex items-center mt-2 text-xs font-medium ${trend.up ? 'text-danger' : 'text-success'}`}>
              <svg className={`w-3 h-3 mr-1 ${trend.up ? '' : 'rotate-180'}`} fill="currentColor" viewBox="0 0 12 12">
                <path d="M6 2l4 5H2z" />
              </svg>
              {trend.value}
            </div>
          )}
        </div>
        <div className={`rounded-lg ${c.bg} p-2.5 ${c.text}`}>
          {icon}
        </div>
      </div>
      <div className={`absolute -bottom-6 -right-6 w-24 h-24 rounded-full opacity-10 ${c.text === 'text-info' ? 'bg-info' : c.text === 'text-danger' ? 'bg-danger' : c.text === 'text-warning' ? 'bg-warning' : c.text === 'text-success' ? 'bg-success' : 'bg-accent-purple'}`} />
    </div>
  );
}
