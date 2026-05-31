"use client";

import React from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';

const regionData = [
  { region: 'Maharashtra', fraud: 342, pct: 22 },
  { region: 'Delhi NCR', fraud: 287, pct: 18 },
  { region: 'Karnataka', fraud: 198, pct: 13 },
  { region: 'Tamil Nadu', fraud: 167, pct: 11 },
  { region: 'Gujarat', fraud: 134, pct: 9 },
  { region: 'UP', fraud: 121, pct: 8 },
  { region: 'Rajasthan', fraud: 98, pct: 6 },
  { region: 'Others', fraud: 157, pct: 13 },
];

const barColors = ['#ef4444', '#f97316', '#f59e0b', '#eab308', '#84cc16', '#22c55e', '#14b8a6', '#64748b'];

const CustomTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const d = payload[0].payload;
    return (
      <div className="rounded-lg border border-surface-lighter bg-surface p-3 shadow-xl">
        <p className="text-xs font-medium text-slate-400 mb-1">{d.region}</p>
        <p className="text-sm font-bold text-warning">{d.fraud} flagged sessions</p>
        <p className="text-xs text-slate-500">{d.pct}% of total</p>
      </div>
    );
  }
  return null;
};

export default function RegionalFraudChart() {
  return (
    <div className="rounded-xl border border-surface-light bg-surface p-5 shadow-lg">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-300">Fraud by Region</h3>
        <span className="text-xs text-slate-500">Top 8</span>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={regionData} layout="vertical" margin={{ top: 0, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
            <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis
              dataKey="region"
              type="category"
              tick={{ fill: '#94a3b8', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={85}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(30,41,59,0.5)' }} />
            <Bar dataKey="fraud" radius={[0, 4, 4, 0]} barSize={18}>
              {regionData.map((_, i) => (
                <Cell key={i} fill={barColors[i]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
