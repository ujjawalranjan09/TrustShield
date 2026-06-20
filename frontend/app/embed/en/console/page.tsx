'use client'

import { useSearchParams } from 'next/navigation'
import { useState, useEffect, useCallback } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ScanEvent {
  id: number
  session_id: string
  scan_type: string
  risk_score: number | null
  risk_level: string | null
  action_taken: string | null
  entities_found: number
  processing_time_ms: number | null
  created_at: string
}

export default function EmbedConsole() {
  const searchParams = useSearchParams()
  const token = searchParams.get('token')
  const [activeTab, setActiveTab] = useState<'scan' | 'reputation' | 'investigation'>('scan')
  const [scanEvents, setScanEvents] = useState<ScanEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const apiHeaders = useCallback(() => ({
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
  }), [token])

  useEffect(() => {
    if (!token) {
      setError('Missing embed token. Access via iframe with ?token=... parameter.')
      return
    }
  }, [token])

  useEffect(() => {
    if (!token || activeTab !== 'scan') return

    setLoading(true)
    fetch(`${API_BASE}/api/v1/scan/recent`, { headers: apiHeaders() })
      .then(r => {
        if (!r.ok) throw new Error('Failed to load scan events')
        return r.json()
      })
      .then(data => setScanEvents(Array.isArray(data) ? data : data.events || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [token, activeTab, apiHeaders])

  if (!token) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-center p-8">
          <h1 className="text-xl font-semibold text-gray-900 mb-2">Embed Console</h1>
          <p className="text-gray-500">Invalid or missing embed token.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200 px-6 py-3">
        <div className="flex items-center gap-6">
          <h1 className="text-sm font-semibold text-gray-900">TrustShield Console</h1>
          <nav className="flex gap-1">
            {(['scan', 'reputation', 'investigation'] as const).map(tab => (
              <button
                key={tab}
                onClick={() => { setActiveTab(tab); setError(null) }}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  activeTab === tab
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </nav>
        </div>
      </div>

      <div className="p-6 max-w-5xl mx-auto">
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
            {error}
          </div>
        )}

        {activeTab === 'scan' && (
          <div>
            <h2 className="text-sm font-medium text-gray-900 mb-4">Recent Scans</h2>
            {loading ? (
              <p className="text-sm text-gray-500">Loading...</p>
            ) : scanEvents.length === 0 ? (
              <p className="text-sm text-gray-500">No scan events found.</p>
            ) : (
              <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium text-gray-500">Type</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500">Risk</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500">Action</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500">Entities</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500">Latency</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-500">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {scanEvents.map(event => (
                      <tr key={event.id} className="hover:bg-gray-50">
                        <td className="px-3 py-2">{event.scan_type}</td>
                        <td className="px-3 py-2">
                          <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium ${
                            event.risk_level === 'CRITICAL' ? 'bg-red-100 text-red-700' :
                            event.risk_level === 'HIGH' ? 'bg-orange-100 text-orange-700' :
                            event.risk_level === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' :
                            'bg-green-100 text-green-700'
                          }`}>
                            {event.risk_level || '—'}
                          </span>
                        </td>
                        <td className="px-3 py-2">{event.action_taken || '—'}</td>
                        <td className="px-3 py-2">{event.entities_found}</td>
                        <td className="px-3 py-2">{event.processing_time_ms ?? '—'}ms</td>
                        <td className="px-3 py-2 text-gray-500">
                          {new Date(event.created_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'reputation' && (
          <div className="text-center py-12">
            <h2 className="text-sm font-medium text-gray-900 mb-2">Reputation Lookup</h2>
            <p className="text-xs text-gray-500">Enter an entity value to check reputation.</p>
            <div className="mt-4 max-w-md mx-auto">
              <input
                type="text"
                placeholder="Enter UPI ID, phone, or entity..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        )}

        {activeTab === 'investigation' && (
          <div className="text-center py-12">
            <h2 className="text-sm font-medium text-gray-900 mb-2">Investigation</h2>
            <p className="text-xs text-gray-500">View and manage fraud investigations for your organization.</p>
          </div>
        )}
      </div>
    </div>
  )
}
