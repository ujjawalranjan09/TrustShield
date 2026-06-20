"use client"

import React, { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Shield, AlertTriangle, Phone, Banknote } from "lucide-react"

const MOCK_INTERVENTIONS = [
  { id: 1, type: "whatsapp_warning", entity: "+91****3210", risk: 0.87, status: "sent", timestamp: "2026-06-19 14:23:00", details: "Scam call detected — OTP phishing attempt. Entity linked to 3 prior reports." },
  { id: 2, type: "bank_freeze_request", entity: "user@ok****", risk: 0.94, status: "dashboard_only", timestamp: "2026-06-19 15:01:00", details: "High-risk UPI transaction to known mule account. No webhook configured." },
  { id: 3, type: "cool_off", entity: "+91****7890", risk: 0.72, status: "triggered", timestamp: "2026-06-19 16:45:00", details: "Cooldown period initiated for coached victim." },
  { id: 4, type: "callback_request", entity: "+91****5555", risk: 0.81, status: "completed", timestamp: "2026-06-18 09:12:00", details: "Callback completed — victim confirmed scam." },
  { id: 5, type: "bank_freeze_request", entity: "+91****1111", risk: 0.96, status: "sent", timestamp: "2026-06-18 11:30:00", details: "Freeze request sent to ICICI via webhook. TTL 3600s." },
]

const TYPE_LABELS: Record<string, { label: string; icon: React.ReactNode }> = {
  whatsapp_warning: { label: "WhatsApp Warning", icon: <Phone className="h-3.5 w-3.5" /> },
  bank_freeze_request: { label: "Bank Freeze", icon: <Banknote className="h-3.5 w-3.5" /> },
  cool_off: { label: "Cool Off", icon: <AlertTriangle className="h-3.5 w-3.5" /> },
  callback_request: { label: "Callback", icon: <Phone className="h-3.5 w-3.5" /> },
}

const STATUS_VARIANT: Record<string, string> = {
  sent: "success",
  dashboard_only: "warning",
  triggered: "info",
  completed: "success",
  failed: "destructive",
}

export default function InterventionPage() {
  const [typeFilter, setTypeFilter] = useState<string>("all")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const filtered = MOCK_INTERVENTIONS.filter((i) => {
    if (typeFilter !== "all" && i.type !== typeFilter) return false
    if (statusFilter !== "all" && i.status !== statusFilter) return false
    return true
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Intervention Dashboard</h1>
        <p className="text-sm text-muted-foreground">Monitor and trigger victim interventions</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <select
          className="border rounded px-2 py-1 text-sm"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          <option value="all">All Types</option>
          <option value="whatsapp_warning">WhatsApp Warning</option>
          <option value="bank_freeze_request">Bank Freeze</option>
          <option value="cool_off">Cool Off</option>
          <option value="callback_request">Callback</option>
        </select>
        <select
          className="border rounded px-2 py-1 text-sm"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="all">All Statuses</option>
          <option value="sent">Sent</option>
          <option value="dashboard_only">Dashboard Only</option>
          <option value="triggered">Triggered</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <Shield className="h-4 w-4" /> Intervention Log
          </CardTitle>
          <div className="flex gap-2">
            <Button size="sm" variant="outline">Send WhatsApp Warning</Button>
            <Button size="sm" variant="outline">Request Bank Freeze</Button>
          </div>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 font-medium">Type</th>
                <th className="py-2 font-medium">Entity</th>
                <th className="py-2 font-medium">Risk</th>
                <th className="py-2 font-medium">Status</th>
                <th className="py-2 font-medium">Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => {
                const meta = TYPE_LABELS[item.type] ?? { label: item.type, icon: null }
                return (
                  <React.Fragment key={item.id}>
                    <tr
                      className="border-b cursor-pointer hover:bg-muted/50"
                      onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                    >
                      <td className="py-2 flex items-center gap-1.5">
                        {meta.icon} {meta.label}
                      </td>
                      <td className="py-2 font-mono text-xs">{item.entity}</td>
                      <td className="py-2">{item.risk.toFixed(2)}</td>
                      <td className="py-2">
                        <Badge variant={STATUS_VARIANT[item.status] as any}>{item.status}</Badge>
                      </td>
                      <td className="py-2 text-muted-foreground">{item.timestamp}</td>
                    </tr>
                    {expandedId === item.id && (
                      <tr>
                        <td colSpan={5} className="px-4 py-3 bg-muted/30 text-xs text-muted-foreground">
                          {item.details}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <div className="text-xs text-muted-foreground border rounded p-3 bg-muted/30">
        <strong>Real-time updates:</strong> WebSocket integration point — connect to
        <code> ws://api/intervention/stream</code> for live InterventionLog events.
        Replace mock data with <code>GET /v1/banker/interventions</code> once backend is connected.
      </div>
    </div>
  )
}
