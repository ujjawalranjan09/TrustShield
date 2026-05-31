"use client";

import React from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

const trendData = [
  { time: '6 AM', fraud: 12, legit: 890 },
  { time: '8 AM', fraud: 45, legit: 2340 },
  { time: '10 AM', fraud: 89, legit: 4120 },
  { time: '12 PM', fraud: 156, legit: 5800 },
  { time: '2 PM', fraud: 134, legit: 5200 },
  { time: '4 PM', fraud: 98, legit: 4700 },
  { time: '6 PM', fraud: 178, legit: 6100 },
  { time: '8 PM', fraud: 210, legit: 7200 },
  { time: '10 PM', fraud: 142, legit: 4900 },
  { time: 'Now', fraud: 87, legit: 3800 },
];

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-lg border border-surface-lighter bg-surface p-3 shadow-xl">
        <p className="text-xs font-medium text-slate-400 mb-1">{label}</p>
        <p className="text-sm font-bold text-danger">Fraud: {payload[0].value.toLocaleString()}</p>
        <p className="text-sm font-bold text-info">Legitimate: {payload[1].value.toLocaleString()}</p>
      </div>
    );
  }
  return null;
};

export default function FraudTrendChart() {
  return (
    <div className="rounded-xl border border-surface-light bg-surface p-5 shadow-lg">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-300">Fraud vs Legitimate Transactions</h3>
        <span className="text-xs text-slate-500">Today</span>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={trendData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="gradientFraud" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#ef4444" stopOpacity={0.4} />
                <stop offset="100%" stopColor="#ef4444" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gradientLegit" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2} />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              verticalAlign="top"
              height={30}
              wrapperStyle={{ fontSize: 11, color: '#94a3b8' }}
            />
            <Area
              type="monotone"
              dataKey="fraud"
              stroke="#ef4444"
              strokeWidth={2}
              fill="url(#gradientFraud)"
              name="Fraud"
            />
            <Area
              type="monotone"
              dataKey="legit"
              stroke="#3b82f6"
              strokeWidth={2}
              fill="url(#gradientLegit)"
              name="Legitimate"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
