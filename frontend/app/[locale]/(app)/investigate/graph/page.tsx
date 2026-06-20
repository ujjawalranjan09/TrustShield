"use client"

import React from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Network } from "lucide-react"

export default function GraphExplorerPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Graph Explorer</h1>
        <p className="text-sm text-muted-foreground">Interactive entity relationship graph</p>
      </div>
      <Card>
        <CardContent className="pt-6">
          <div className="h-[500px] flex items-center justify-center text-muted-foreground border border-dashed rounded-lg">
            <div className="text-center">
              <Network className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <p className="text-lg font-medium">Graph Visualization</p>
              <p className="text-sm mt-1">Use the Network Investigation page for the full force-directed graph</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => window.location.href = "/en/investigate/network"}
              >
                <Network className="h-4 w-4 mr-1" />
                Open Network Investigation
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
