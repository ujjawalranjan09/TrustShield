"use client"

import React from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

export default function RecoveryPage() {
  const cases = [
    { id: "RC-001", type: "vishing", amount: "₹50,000", status: "pending", deadline: "2 days" },
    { id: "RC-002", type: "upi_fraud", amount: "₹25,000", status: "in_progress", deadline: "5 days" },
    { id: "RC-003", type: "remote_access", amount: "₹1,00,000", status: "completed", deadline: "—" },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Recovery Cases</h1>
        <p className="text-sm text-muted-foreground">Track and manage fraud recovery cases</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {["pending", "in_progress", "completed"].map((status) => (
          <Card key={status}>
            <CardHeader>
              <CardTitle className="text-sm capitalize">{status.replace("_", " ")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {cases.filter(c => c.status === status).map((c) => (
                <div key={c.id} className="p-3 rounded-lg bg-muted/50 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{c.id}</span>
                    <Badge variant={status === "completed" ? "success" : status === "pending" ? "warning" : "info"}>{c.type.replace("_", " ")}</Badge>
                  </div>
                  <p className="text-sm">{c.amount}</p>
                  <p className="text-xs text-muted-foreground">Deadline: {c.deadline}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
