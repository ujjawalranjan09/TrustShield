"use client"

import React from "react"
import { useTranslations } from "next-intl"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Search, Filter } from "lucide-react"

export default function SessionsPage() {
  const t = useTranslations("investigate")

  const mockSessions = [
    { id: "S-1001", risk: "CRITICAL", type: "vishing", entity: "+919876543210", time: "2 min ago", verdict: "pending" },
    { id: "S-1002", risk: "HIGH", type: "remote_access", entity: "anydesk@scam", time: "5 min ago", verdict: "pending" },
    { id: "S-1003", risk: "MEDIUM", type: "refund_scam", entity: "qr-scan@pay", time: "12 min ago", verdict: "false_positive" },
    { id: "S-1004", risk: "LOW", type: "unknown", entity: "friend@chat", time: "1 hr ago", verdict: "true_positive" },
    { id: "S-1005", risk: "CRITICAL", type: "otp_harvesting", entity: "+919123456789", time: "2 hr ago", verdict: "pending" },
  ]

  const getVariant = (risk: string) => {
    switch (risk) {
      case "CRITICAL": return "destructive" as const
      case "HIGH": return "warning" as const
      case "MEDIUM": return "info" as const
      default: return "success" as const
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("sessionsTitle")}</h1>
          <p className="text-sm text-muted-foreground">Browse and investigate analysis sessions</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm"><Filter className="h-4 w-4 mr-1" /> Filter</Button>
          <Button variant="outline" size="sm"><Search className="h-4 w-4 mr-1" /> Search</Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="divide-y">
            {mockSessions.map((session) => (
              <div key={session.id} className="flex items-center justify-between p-4 hover:bg-muted/50 cursor-pointer transition-colors">
                <div className="flex items-center gap-4">
                  <div>
                    <p className="font-medium text-sm">{session.id}</p>
                    <p className="text-xs text-muted-foreground">{session.time}</p>
                  </div>
                  <Badge variant={getVariant(session.risk)}>{session.risk}</Badge>
                  <div>
                    <p className="text-sm">{session.type.replace("_", " ")}</p>
                    <p className="text-xs text-muted-foreground">{session.entity}</p>
                  </div>
                </div>
                <Badge variant={session.verdict === "pending" ? "secondary" : session.verdict === "false_positive" ? "warning" : "success"}>
                  {session.verdict.replace("_", " ")}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
