"use client"

import React, { useState } from "react"
import { useTranslations } from "next-intl"
import { useMutation } from "@tanstack/react-query"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Loader2, ShieldAlert, ShieldCheck, AlertTriangle } from "lucide-react"

interface ScanResult {
  result: {
    is_scam: boolean
    confidence: number
    scam_type: string
    risk_level: string
    risk_score: number
    flagged_entities: Array<{ entity_type: string; value: string; confidence_score: number }>
    warning_message_en: string | null
    warning_message_hi: string | null
    recommendation: string
    processing_time_ms: number
  }
  user_message_en: string
  user_message_hi: string
}

const SAMPLE_MESSAGES = [
  { label: "OTP Scam", text: "Hello sir, I am calling from bank. aapka debit card block ho gaya hai. Please share your OTP verify karne ke liye." },
  { label: "AnyDesk Scam", text: "Aapko refund process karne ke liye ek baar screen share karo. AnyDesk app download kijiye aur code bataiye: 123456789." },
  { label: "QR Code Scam", text: "Sir, your refund of Rs 5000 is approved. Please scan this QR code. Payment receive karne ke liye PIN enter karein." },
  { label: "Legitimate", text: "Hi, when will my order be delivered? Your order will be delivered by tomorrow 8 PM." },
]

export default function ScanPage() {
  const t = useTranslations("scan")
  const [message, setMessage] = useState("")

  const scanMutation = useMutation({
    mutationFn: async (text: string) => {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/scan-message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      })
      if (!res.ok) throw new Error("Scan failed")
      return res.json() as Promise<ScanResult>
    },
  })

  const getRiskColor = (level: string) => {
    switch (level) {
      case "CRITICAL": return "destructive"
      case "HIGH": return "warning"
      case "MEDIUM": return "info"
      default: return "success"
    }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={(e) => { e.preventDefault(); if (message.trim()) scanMutation.mutate(message) }} className="space-y-4">
            <Textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder={t("placeholder")}
              rows={5}
              className="resize-none"
            />
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={scanMutation.isPending || !message.trim()}>
                {scanMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> {t("scanning")}</>
                ) : t("scanButton")}
              </Button>
              <span className="text-xs text-muted-foreground">{t("poweredBy")}</span>
            </div>
          </form>
        </CardContent>
      </Card>

      <div>
        <p className="text-sm font-medium text-muted-foreground mb-3">{t("trySample")}</p>
        <div className="flex flex-wrap gap-2">
          {SAMPLE_MESSAGES.map((sample, i) => (
            <Button key={i} variant="outline" size="sm" onClick={() => setMessage(sample.text)}>
              {sample.label}
            </Button>
          ))}
        </div>
      </div>

      {scanMutation.isError && (
        <Card className="border-destructive/20 bg-destructive/5">
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">{scanMutation.error.message}</p>
          </CardContent>
        </Card>
      )}

      {scanMutation.data && (
        <div className="space-y-4">
          <Card className={`border-${getRiskColor(scanMutation.data.result.risk_level)}/20 bg-${getRiskColor(scanMutation.data.result.risk_level)}/5`}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  {scanMutation.data.result.is_scam ? (
                    <><ShieldAlert className="h-5 w-5" /> {t("scamDetected")}</>
                  ) : (
                    <><ShieldCheck className="h-5 w-5" /> {t("appearsSafe")}</>
                  )}
                </CardTitle>
                <div className="text-right">
                  <div className="text-3xl font-bold">{scanMutation.data.result.risk_score}</div>
                  <div className="text-xs text-muted-foreground">/ 100</div>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">{t("riskLevel")}</p>
                  <Badge variant={getRiskColor(scanMutation.data.result.risk_level) as any}>{scanMutation.data.result.risk_level}</Badge>
                </div>
                <div>
                  <p className="text-muted-foreground">{t("confidence")}</p>
                  <p className="font-medium">{(scanMutation.data.result.confidence * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-muted-foreground">{t("scamType")}</p>
                  <p className="font-medium">{scanMutation.data.result.scam_type.replace("_", " ")}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">{t("processingTime")}</p>
                  <p className="font-medium">{scanMutation.data.result.processing_time_ms}ms</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {(scanMutation.data.result.warning_message_en || scanMutation.data.result.warning_message_hi) && (
            <Card>
              <CardHeader><CardTitle className="text-sm">{t("warnings")}</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {scanMutation.data.result.warning_message_en && <p className="text-sm">{scanMutation.data.result.warning_message_en}</p>}
                {scanMutation.data.result.warning_message_hi && <p className="text-sm text-muted-foreground">{scanMutation.data.result.warning_message_hi}</p>}
              </CardContent>
            </Card>
          )}

          {scanMutation.data.result.flagged_entities.length > 0 && (
            <Card>
              <CardHeader><CardTitle className="text-sm">{t("flaggedEntities")}</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {scanMutation.data.result.flagged_entities.map((entity, i) => (
                    <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                      <div>
                        <p className="text-sm font-medium">{entity.value}</p>
                        <p className="text-xs text-muted-foreground">{entity.entity_type}</p>
                      </div>
                      <span className="text-xs text-muted-foreground">{(entity.confidence_score * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader><CardTitle className="text-sm">{t("recommendation")}</CardTitle></CardHeader>
            <CardContent><p className="text-sm">{scanMutation.data.result.recommendation}</p></CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
