"use client"

import React, { useEffect, useState } from "react"
import { useTranslations } from "next-intl"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

interface UsageData {
  scan_calls: number
  webhook_calls: number
  scan_limit: number
  webhook_limit: number
  remaining_scan: number
  remaining_webhook: number
  percent_used: number
  bucket: string
}

interface SubscriptionData {
  plan_code: string
  status: string
  current_period_end: string | null
  stripe_customer_id: string | null
}

export default function BillingPage() {
  const t = useTranslations("billing")
  const [usage, setUsage] = useState<UsageData | null>(null)
  const [subscription, setSubscription] = useState<SubscriptionData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [usageRes, subRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/v1/billing/usage`, { credentials: "include" }),
          fetch(`${API_BASE_URL}/api/v1/billing/subscription`, { credentials: "include" }),
        ])
        if (usageRes.ok) setUsage(await usageRes.json())
        if (subRes.ok) setSubscription(await subRes.json())
      } catch {
        setError("Failed to load billing data")
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  const handleUpgrade = async (priceId: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/billing/checkout`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          price_id: priceId,
          success_url: `${window.location.origin}/dashboard/billing?success=true`,
          cancel_url: `${window.location.origin}/dashboard/billing`,
        }),
      })
      if (res.ok) {
        const { url } = await res.json()
        window.location.href = url
      }
    } catch {
      setError("Failed to start checkout")
    }
  }

  const handleManage = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/billing/portal`, {
        method: "POST",
        credentials: "include",
      })
      if (res.ok) {
        const { url } = await res.json()
        window.location.href = url
      }
    } catch {
      setError("Failed to open billing portal")
    }
  }

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-6 md:grid-cols-2">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-2xl font-bold">{t("title", { defaultValue: "Billing" })}</h1>

      {error && (
        <div className="bg-destructive/10 border border-destructive/30 rounded-lg px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        {/* Current Plan */}
        <Card>
          <CardHeader>
            <CardTitle>{t("currentPlan", { defaultValue: "Current Plan" })}</CardTitle>
            <CardDescription>{subscription?.plan_code?.toUpperCase() || "FREE"}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Status: <span className="font-medium text-foreground">{subscription?.status || "active"}</span>
            </div>
            {subscription?.current_period_end && (
              <div className="text-sm text-muted-foreground">
                Period ends: {new Date(subscription.current_period_end).toLocaleDateString()}
              </div>
            )}
            <div className="flex gap-2">
              <Button variant="outline" onClick={handleManage}>
                {t("manage", { defaultValue: "Manage Subscription" })}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Usage */}
        <Card>
          <CardHeader>
            <CardTitle>{t("usage", { defaultValue: "Usage This Month" })}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span>Scans</span>
                <span>{usage?.scan_calls || 0} / {usage?.scan_limit === -1 ? "∞" : usage?.scan_limit}</span>
              </div>
              <div className="h-2 bg-secondary rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full"
                  style={{ width: `${Math.min(100, usage?.percent_used || 0)}%` }}
                />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span>Webhooks</span>
                <span>{usage?.webhook_calls || 0} / {usage?.webhook_limit === -1 ? "∞" : usage?.webhook_limit}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Upgrade Options */}
      <Card>
        <CardHeader>
          <CardTitle>{t("upgrade", { defaultValue: "Upgrade Plan" })}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            <Button variant="outline" onClick={() => handleUpgrade("price_pro")}>
              Pro — 50k scans/mo
            </Button>
            <Button variant="outline" onClick={() => handleUpgrade("price_bank")}>
              Bank — 1M scans/mo
            </Button>
            <Button variant="outline" onClick={() => handleUpgrade("price_enterprise")}>
              Enterprise — Unlimited
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
