"use client"

import React from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export default function HotspotsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Fraud Hotspots Map</h1>
        <p className="text-sm text-muted-foreground">Geographic distribution of fraud activity across India</p>
      </div>
      <Card>
        <CardContent className="pt-6">
          <div className="h-[500px] flex items-center justify-center text-muted-foreground border border-dashed rounded-lg">
            <div className="text-center">
              <p className="text-lg font-medium">India Choropleth Map</p>
              <p className="text-sm mt-1">react-simple-maps will be rendered here</p>
              <p className="text-xs mt-2">Lazy-loaded (~200 KB) — only loaded on this page</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
