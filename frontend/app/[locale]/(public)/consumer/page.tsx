"use client"

import React, { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Shield, AlertTriangle, Phone, ExternalLink } from "lucide-react"

export default function ConsumerPage() {
  const [message, setMessage] = useState("")
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const handleScan = async () => {
    if (!message.trim()) return
    setLoading(true)
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/consumer/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: message, language: "hi" }),
      })
      if (!res.ok) throw new Error("Scan failed")
      setResult(await res.json())
    } catch {
      setResult({ error: "Scan failed. Please try again." })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center px-4 py-8">
      <div className="w-full max-w-lg space-y-6">
        <div className="text-center">
          <Shield className="h-12 w-12 mx-auto text-primary mb-3" />
          <h1 className="text-2xl font-bold">TrustShield Scanner</h1>
          <p className="text-sm text-muted-foreground mt-1">Suspicious message check karein</p>
        </div>

        <Card>
          <CardContent className="pt-6 space-y-4">
            <Textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Yahan suspicious message paste karein..."
              rows={4}
              className="resize-none"
            />
            <Button onClick={handleScan} disabled={loading || !message.trim()} className="w-full">
              {loading ? "Checking..." : "Scan Message / संदेश जांचें"}
            </Button>
          </CardContent>
        </Card>

        {result && !result.error && (
          <Card className={`border-${result.risk_level === "CRITICAL" ? "destructive" : result.risk_level === "HIGH" ? "warning" : "success"}/20`}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-lg">
                  {result.risk_score >= 40 ? <AlertTriangle className="h-5 w-5" /> : <Shield className="h-5 w-5" />}
                  {result.risk_score >= 40 ? "Scam Alert!" : "Looks Safe"}
                </CardTitle>
                <div className="text-2xl font-bold">{result.risk_score}/100</div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {result.warning_hi && (
                <div className="p-3 rounded-lg bg-destructive/10 text-sm">{result.warning_hi}</div>
              )}
              {result.warning_en && result.warning_en !== result.warning_hi && (
                <div className="p-3 rounded-lg bg-muted text-sm text-muted-foreground">{result.warning_en}</div>
              )}
              {result.recovery_steps && (
                <div>
                  <p className="text-sm font-medium mb-2">Kya karna chahiye:</p>
                  <ul className="space-y-1">
                    {result.recovery_steps.map((step: string, i: number) => (
                      <li key={i} className="text-sm flex items-start gap-2">
                        <span className="text-primary font-bold">{i + 1}.</span> {step}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="flex gap-2 pt-2">
                <a href="tel:1930" className="flex items-center gap-1 text-sm text-primary">
                  <Phone className="h-4 w-4" /> 1930 Call
                </a>
                <a href="https://cybercrime.gov.in" target="_blank" className="flex items-center gap-1 text-sm text-primary">
                  <ExternalLink className="h-4 w-4" /> Cybercrime Portal
                </a>
              </div>
            </CardContent>
          </Card>
        )}

        {result?.error && (
          <Card className="border-destructive/20 bg-destructive/5">
            <CardContent className="pt-6">
              <p className="text-sm text-destructive">{result.error}</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
