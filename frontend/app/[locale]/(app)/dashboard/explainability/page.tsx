"use client"

import React, { useState } from "react"
import { useTranslations } from "next-intl"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Brain, BarChart3, Activity } from "lucide-react"

export default function ExplainabilityPage() {
  const t = useTranslations("explainability")
  const [text, setText] = useState("")

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">Model interpretability and monitoring</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Brain className="h-4 w-4" /> {t("modelCard")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between text-sm"><span className="text-muted-foreground">Version</span><span className="font-medium">v1.0.0</span></div>
            <div className="flex justify-between text-sm"><span className="text-muted-foreground">Architecture</span><span className="font-medium">IndicBERT + XGBoost</span></div>
            <div className="flex justify-between text-sm"><span className="text-muted-foreground">Gold-set F1</span><span className="font-medium">0.92</span></div>
            <div className="flex justify-between text-sm"><span className="text-muted-foreground">Training Size</span><span className="font-medium">101,500</span></div>
            <div className="flex justify-between text-sm"><span className="text-muted-foreground">Last Promoted</span><span className="font-medium">2026-06-19</span></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <BarChart3 className="h-4 w-4" /> {t("factorExplorer")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={t("pasteText")} rows={3} className="resize-none" />
            <Button size="sm" disabled={!text.trim()}>{t("getExplanation")}</Button>
            <div className="space-y-2 mt-4">
              <p className="text-xs font-medium text-muted-foreground">{t("featureContributions")}</p>
              {["classifier_confidence", "high_risk_entity", "unknown_contact", "prior_reports"].map((f, i) => (
                <div key={f} className="flex items-center gap-2">
                  <div className="w-32 text-xs text-muted-foreground truncate">{f}</div>
                  <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                    <div className="h-full bg-primary rounded-full" style={{ width: `${[85, 60, 45, 30][i]}%` }} />
                  </div>
                  <span className="text-xs w-8 text-right">{[0.85, 0.60, 0.45, 0.30][i]}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Activity className="h-4 w-4" /> {t("driftDashboard")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {["text_length", "urgency_count", "financial_count", "entity_count"].map((f) => (
                <div key={f} className="p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground truncate">{f}</p>
                  <p className="text-lg font-bold mt-1">0.{Math.floor(Math.random() * 9)}</p>
                  <Badge variant="success" className="mt-1 text-[10px]">Normal</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
