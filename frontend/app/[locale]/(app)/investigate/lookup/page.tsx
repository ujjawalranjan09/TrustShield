"use client"

import React, { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Search } from "lucide-react"

export default function LookupPage() {
  const [query, setQuery] = useState("")
  const [result, setResult] = useState<any>(null)

  const handleSearch = () => {
    if (!query.trim()) return
    setResult({
      entity_value: query,
      is_flagged: query.includes("scam") || query.includes("+9198"),
      report_count: query.includes("scam") ? 12 : 0,
      risk_level: query.includes("scam") ? "critical" : "low",
    })
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold">Entity Lookup</h1>
        <p className="text-sm text-muted-foreground">Check if an entity has been reported as fraudulent</p>
      </div>

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={(e) => { e.preventDefault(); handleSearch() }} className="flex gap-2">
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Enter phone, UPI ID, or URL..." className="flex-1" />
            <Button type="submit"><Search className="h-4 w-4 mr-1" /> Lookup</Button>
          </form>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Result</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Entity</span>
              <span className="text-sm font-medium">{result.entity_value}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Flagged</span>
              <Badge variant={result.is_flagged ? "destructive" : "success"}>{result.is_flagged ? "Yes" : "No"}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Report Count</span>
              <span className="text-sm font-medium">{result.report_count}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Risk Level</span>
              <Badge variant={result.risk_level === "critical" ? "destructive" : "success"}>{result.risk_level}</Badge>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
