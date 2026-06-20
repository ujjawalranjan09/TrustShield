"use client"

import React from "react"
import { useTranslations } from "next-intl"
import { useQuery } from "@tanstack/react-query"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Shield, AlertTriangle, Ban, CheckCircle, Activity, TrendingUp, TrendingDown } from "lucide-react"

interface DashboardStats {
  total_scans_today: number
  flagged_sessions: number
  entities_blacklisted: number
  false_positive_rate: number
}

async function fetchDashboardStats(): Promise<DashboardStats> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/analytics/dashboard`)
  if (!res.ok) throw new Error("Failed to fetch dashboard stats")
  return res.json()
}

function StatCard({ title, value, icon: Icon, color, trend }: {
  title: string
  value: string
  icon: React.ComponentType<{ className?: string }>
  color: string
  trend?: { value: string; up: boolean }
}) {
  return (
    <Card className={`relative overflow-hidden border-${color}/20 bg-${color}/5`}>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <Icon className={`h-4 w-4 text-${color}`} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {trend && (
          <p className={`text-xs mt-1 ${trend.up ? "text-destructive" : "text-success"}`}>
            {trend.up ? <TrendingUp className="inline h-3 w-3 mr-1" /> : <TrendingDown className="inline h-3 w-3 mr-1" />}
            {trend.value}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const t = useTranslations("dashboard")
  const { data: stats, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: fetchDashboardStats,
    refetchInterval: 15_000,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {isLoading ? (
          <>
            <Skeleton className="h-[120px] rounded-xl" />
            <Skeleton className="h-[120px] rounded-xl" />
            <Skeleton className="h-[120px] rounded-xl" />
            <Skeleton className="h-[120px] rounded-xl" />
          </>
        ) : error ? (
          <Card className="col-span-4 border-warning/20 bg-warning/5">
            <CardContent className="pt-6">
              <div className="flex items-center gap-2 text-warning">
                <AlertTriangle className="h-4 w-4" />
                <span className="text-sm">{t("common:demoMode")} — API offline</span>
              </div>
            </CardContent>
          </Card>
        ) : (
          <>
            <StatCard title={t("scansToday")} value={(stats?.total_scans_today || 0).toLocaleString()} icon={Shield} color="info" trend={{ value: "+12.4% vs yesterday", up: true }} />
            <StatCard title={t("flaggedSessions")} value={(stats?.flagged_sessions || 0).toLocaleString()} icon={AlertTriangle} color="warning" trend={{ value: "+8.2% vs yesterday", up: true }} />
            <StatCard title={t("blacklistedEntities")} value={(stats?.entities_blacklisted || 0).toLocaleString()} icon={Ban} color="destructive" trend={{ value: "-3.1% vs yesterday", up: false }} />
            <StatCard title={t("falsePositiveRate")} value={`${stats?.false_positive_rate || 0}%`} icon={CheckCircle} color="success" trend={{ value: "-0.3% vs yesterday", up: false }} />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4" />
              {t("liveFeed")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                  <div className="flex items-center gap-3">
                    <div className="h-2 w-2 rounded-full bg-success animate-pulse" />
                    <div>
                      <p className="text-sm font-medium">Session #{1000 + i}</p>
                      <p className="text-xs text-muted-foreground">2 min ago</p>
                    </div>
                  </div>
                  <Badge variant={i <= 2 ? "destructive" : i <= 4 ? "warning" : "success"}>
                    {i <= 2 ? "CRITICAL" : i <= 4 ? "HIGH" : "LOW"}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("fraudTrend")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[200px] flex items-center justify-center text-muted-foreground text-sm">
              Chart will be rendered with Recharts
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
