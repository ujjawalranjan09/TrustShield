"use client"

import React from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Shield, FileText, ClipboardList } from "lucide-react"

export default function CompliancePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Compliance</h1>
        <p className="text-sm text-muted-foreground">Regulatory reporting and audit trail</p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><FileText className="h-4 w-4" /> RBI Reports</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {["Q1 2026", "Q4 2025", "Q3 2025"].map((q) => (
              <div key={q} className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                <span className="text-sm">{q}</span>
                <Badge variant="success">Generated</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><Shield className="h-4 w-4" /> Audit Log</CardTitle></CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">Hash-chain verified, append-only audit trail</p>
            <div className="mt-4 space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="text-success">✓</span>
                  <span className="text-muted-foreground">2026-06-1{i} 10:0{i}:00</span>
                  <span>API key rotated</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><ClipboardList className="h-4 w-4" /> 1930 Submissions</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {[1, 2].map((i) => (
                <div key={i} className="p-3 rounded-lg bg-muted/50">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">REF-{1000 + i}</span>
                    <Badge variant="info">Submitted</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Case #{i} — filed on 2026-06-1{i}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
