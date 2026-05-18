"use client";

import React, { useEffect, useState } from 'react';

export default function Dashboard() {
  const [stats, setStats] = useState({
    scansToday: 0,
    flaggedSessions: 0,
    entitiesBlacklisted: 0,
    falsePositiveRate: 0.0,
  });

  const [feed, setFeed] = useState<any[]>([]);

  useEffect(() => {
    // Mock API fetch for stats
    const fetchStats = async () => {
      setStats({
        scansToday: 145023,
        flaggedSessions: 1204,
        entitiesBlacklisted: 89,
        falsePositiveRate: 1.2,
      });
    };
    fetchStats();

    // Mock WebSocket feed
    const interval = setInterval(() => {
      setFeed((prev) => [
        {
          id: Date.now(),
          type: "FREEZE_AND_REPORT",
          message: "High risk session detected (AnyDesk)",
          time: new Date().toLocaleTimeString(),
        },
        ...prev.slice(0, 9), // Keep last 10
      ]);
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-8 font-sans">
      <h1 className="text-3xl font-bold mb-6">TrustShield Dashboard</h1>

      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="p-4 border rounded shadow">
          <p className="text-gray-500 text-sm">Total Scans Today</p>
          <p className="text-2xl font-bold">{stats.scansToday.toLocaleString()}</p>
        </div>
        <div className="p-4 border rounded shadow">
          <p className="text-gray-500 text-sm">Flagged Sessions</p>
          <p className="text-2xl font-bold text-red-600">{stats.flaggedSessions.toLocaleString()}</p>
        </div>
        <div className="p-4 border rounded shadow">
          <p className="text-gray-500 text-sm">Blacklisted Entities</p>
          <p className="text-2xl font-bold text-orange-600">{stats.entitiesBlacklisted.toLocaleString()}</p>
        </div>
        <div className="p-4 border rounded shadow">
          <p className="text-gray-500 text-sm">False Positive Rate</p>
          <p className="text-2xl font-bold text-green-600">{stats.falsePositiveRate}%</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-8">
        <div className="border p-4 rounded shadow">
          <h2 className="text-xl font-bold mb-4">Live Fraud Feed</h2>
          <ul>
            {feed.map((event) => (
              <li key={event.id} className="mb-2 pb-2 border-b last:border-0">
                <span className="text-xs text-gray-400 mr-2">{event.time}</span>
                <span className="font-bold text-red-500 mr-2">[{event.type}]</span>
                <span>{event.message}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="border p-4 rounded shadow">
          <h2 className="text-xl font-bold mb-4">Fraud Trend & Map</h2>
          <div className="h-48 bg-gray-100 flex items-center justify-center mb-4">
            [Line Chart Placeholder - Recharts]
          </div>
          <div className="h-48 bg-gray-100 flex items-center justify-center">
            [Geographic Heatmap Placeholder]
          </div>
        </div>
      </div>
    </div>
  );
}
