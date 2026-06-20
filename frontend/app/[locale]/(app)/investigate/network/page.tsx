"use client"

import React, { useState, useCallback, useRef, useEffect } from "react"
import dynamic from "next/dynamic"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Search, Expand, Network, Eye, ChevronRight, X } from "lucide-react"
import { apiClient } from "@/lib/api"

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false })

interface GraphNode {
  id: string
  label: string
  risk: number
  entity_type: string
  ring_id: string | null
  report_count: number
  propagated_risk: number
  fx?: number
  fy?: number
}

interface GraphEdge {
  source: string | GraphNode
  target: string | GraphNode
  label: string
  weight: number
}

interface NeighborhoodData {
  center: GraphNode
  nodes: GraphNode[]
  edges: GraphEdge[]
  ring_memberships: Array<{ ring_id: string; risk_level: string; entity_count: number; status: string }>
  direct_risk: number
  propagated_risk: number
}

interface RingSummary {
  ring_id: string
  entity_count: number
  total_reports: number
  top_scam_type: string | null
  risk_level: string
  status: string
  detected_at: string
}

function riskColor(risk: number): string {
  if (risk >= 0.7) return "#ef4444"
  if (risk >= 0.4) return "#f59e0b"
  return "#22c55e"
}

function riskGradient(risk: number): string {
  if (risk >= 0.7) return "from-red-500/20 to-red-900/10"
  if (risk >= 0.4) return "from-amber-500/20 to-amber-900/10"
  return "from-green-500/20 to-green-900/10"
}

function GraphCanvas({
  data,
  onNodeClick,
  onExpand,
  depth,
}: {
  data: NeighborhoodData
  onNodeClick: (node: GraphNode) => void
  onExpand: () => void
  depth: number
}) {
  const fgRef = useRef<any>(null)

  const graphData = React.useMemo(() => {
    const nodeMap = new Map<string, GraphNode>()
    for (const n of data.nodes) {
      nodeMap.set(n.id, { ...n })
    }
    return {
      nodes: data.nodes.map((n) => ({ ...n })),
      links: data.edges.map((e) => ({
        source: typeof e.source === "string" ? e.source : e.source.id,
        target: typeof e.target === "string" ? e.target : e.target.id,
        weight: e.weight,
        label: e.label,
      })),
    }
  }, [data])

  const nodeCanvasObject = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const label = node.label
      const fontSize = Math.max(10 / globalScale, 2)
      const size = Math.max(5, node.risk * 15 + 4)
      const color = riskColor(node.risk || 0)

      ctx.beginPath()
      ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
      ctx.fillStyle = color
      ctx.fill()

      if (node.ring_id) {
        ctx.beginPath()
        ctx.arc(node.x, node.y, size + 3, 0, 2 * Math.PI)
        ctx.strokeStyle = "#a855f7"
        ctx.lineWidth = 2
        ctx.stroke()
      }

      ctx.font = `${fontSize}px Sans-Serif`
      ctx.textAlign = "center"
      ctx.textBaseline = "top"
      ctx.fillStyle = "rgba(255,255,255,0.9)"
      ctx.fillText(label, node.x, node.y + size + 2)
    },
    []
  )

  const handleNodeClick = useCallback(
    (node: any) => {
      onNodeClick(node as GraphNode)
    },
    [onNodeClick]
  )

  return (
    <div className="relative w-full h-full">
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        nodeCanvasObject={nodeCanvasObject}
        nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
          const size = Math.max(5, (node.risk || 0) * 15 + 4)
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
          ctx.fill()
        }}
        linkWidth={(link: any) => Math.max(1, (link.weight || 1) * 0.5)}
        linkColor={() => "rgba(148,163,184,0.4)"}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        onNodeClick={handleNodeClick}
        backgroundColor="rgba(0,0,0,0)"
        width={800}
        height={600}
        d3VelocityDecay={0.3}
      />
      {depth < 3 && (
        <Button
          size="sm"
          variant="outline"
          className="absolute bottom-3 right-3 bg-background/80 backdrop-blur"
          onClick={onExpand}
        >
          <Expand className="h-4 w-4 mr-1" />
          Expand (+1 hop)
        </Button>
      )}
    </div>
  )
}

function NodeDetailPanel({
  node,
  data,
  onClose,
}: {
  node: GraphNode
  data: NeighborhoodData
  onClose: () => void
}) {
  const riskBadge = (risk: number) => {
    if (risk >= 0.7) return "destructive" as const
    if (risk >= 0.4) return "warning" as const
    return "success" as const
  }

  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Entity Details</CardTitle>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="text-xs text-muted-foreground mb-1">Label</p>
          <p className="text-sm font-mono font-medium">{node.label}</p>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Type</span>
          <Badge variant="secondary">{node.entity_type}</Badge>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Direct Risk</span>
          <Badge variant={riskBadge(node.risk)}>{(node.risk * 100).toFixed(0)}%</Badge>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Propagated Risk</span>
          <Badge variant={riskBadge(node.propagated_risk)}>
            {(node.propagated_risk * 100).toFixed(0)}%
          </Badge>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Report Count</span>
          <span className="text-sm font-medium">{node.report_count}</span>
        </div>
        {node.ring_id && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Ring</span>
            <Badge variant="info">{node.ring_id}</Badge>
          </div>
        )}
        {data.ring_memberships.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-2">Ring Memberships</p>
            {data.ring_memberships.map((rm) => (
              <div key={rm.ring_id} className="flex items-center justify-between text-xs py-1">
                <span className="font-mono">{rm.ring_id}</span>
                <Badge variant={rm.risk_level === "critical" ? "destructive" : "warning"}>
                  {rm.risk_level}
                </Badge>
              </div>
            ))}
          </div>
        )}
        <div className="pt-2 border-t">
          <p className="text-xs text-muted-foreground mb-1">Connected Nodes</p>
          <p className="text-sm font-medium">{data.nodes.length - 1} neighbors</p>
        </div>
      </CardContent>
    </Card>
  )
}

function RingsList({
  onSelectRing,
}: {
  onSelectRing: (ringId: string) => void
}) {
  const [rings, setRings] = useState<RingSummary[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)

  const fetchRings = useCallback(async (p: number) => {
    setLoading(true)
    try {
      const data = await apiClient.getFraudRisks(p, 20)
      setRings(data.rings)
      setTotal(data.total)
    } catch {
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchRings(page)
  }, [page, fetchRings])

  const riskBadge = (risk: string) => {
    switch (risk) {
      case "critical": return "destructive" as const
      case "high": return "warning" as const
      default: return "secondary" as const
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">{total} rings detected</p>
      </div>
      {loading && <p className="text-xs text-muted-foreground">Loading...</p>}
      <ScrollArea className="h-[calc(100vh-300px)]">
        <div className="space-y-2">
          {rings.map((ring) => (
            <div
              key={ring.ring_id}
              className="p-3 rounded-lg border bg-card hover:bg-accent/50 cursor-pointer transition-colors"
              onClick={() => onSelectRing(ring.ring_id)}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-mono font-medium">{ring.ring_id}</span>
                <Badge variant={riskBadge(ring.risk_level)}>{ring.risk_level}</Badge>
              </div>
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <span>{ring.entity_count} entities</span>
                <span>{ring.total_reports} reports</span>
                {ring.top_scam_type && <span>{ring.top_scam_type}</span>}
              </div>
              <div className="flex items-center justify-between mt-1">
                <Badge variant={ring.status === "confirmed" ? "destructive" : "secondary"}>
                  {ring.status}
                </Badge>
                <ChevronRight className="h-3 w-3 text-muted-foreground" />
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
      {total > 20 && (
        <div className="flex justify-between">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </Button>
          <span className="text-xs text-muted-foreground self-center">
            Page {page} / {Math.ceil(total / 20)}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page * 20 >= total}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  )
}

export default function NetworkInvestigationPage() {
  const [searchQuery, setSearchQuery] = useState("")
  const [entityType, setEntityType] = useState("PHONE")
  const [data, setData] = useState<NeighborhoodData | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [depth, setDepth] = useState(2)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<"graph" | "rings">("graph")

  const fetchNeighborhood = useCallback(async (entityValue: string, entityTypeVal: string, d: number) => {
    setLoading(true)
    setError(null)
    try {
      const result = await apiClient.getEntityNeighborhood(entityTypeVal, entityValue, d)
      setData(result)
    } catch (err: any) {
      setError(err.message || "Failed to load graph")
    } finally {
      setLoading(false)
    }
  }, [])

  const handleSearch = () => {
    if (!searchQuery.trim()) return
    setDepth(2)
    fetchNeighborhood(searchQuery, entityType, 2)
  }

  const handleExpand = () => {
    if (!data || !searchQuery) return
    const newDepth = depth + 1
    setDepth(newDepth)
    fetchNeighborhood(searchQuery, entityType, newDepth)
  }

  const handleNodeClick = (node: GraphNode) => {
    setSelectedNode(node)
  }

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-3">
          <Network className="h-5 w-5 text-muted-foreground" />
          <div>
            <h1 className="text-lg font-bold">Network Investigation</h1>
            <p className="text-xs text-muted-foreground">
              Force-directed graph of entity relationships
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant={view === "graph" ? "default" : "outline"}
            size="sm"
            onClick={() => setView("graph")}
          >
            <Network className="h-4 w-4 mr-1" />
            Graph
          </Button>
          <Button
            variant={view === "rings" ? "default" : "outline"}
            size="sm"
            onClick={() => setView("rings")}
          >
            <Eye className="h-4 w-4 mr-1" />
            Rings
          </Button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col">
          <div className="p-3 border-b">
            <form
              onSubmit={(e) => {
                e.preventDefault()
                handleSearch()
              }}
              className="flex gap-2"
            >
              <select
                value={entityType}
                onChange={(e) => setEntityType(e.target.value)}
                className="h-9 rounded-md border bg-background px-3 text-sm"
              >
                <option value="PHONE">Phone</option>
                <option value="UPI">UPI</option>
                <option value="ANYDESK">AnyDesk</option>
                <option value="TEAMVIEWER">TeamViewer</option>
                <option value="URL_SHORTLINK">URL</option>
                <option value="IFSC">IFSC</option>
              </select>
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Enter entity value to investigate..."
                className="flex-1"
              />
              <Button type="submit" size="sm" disabled={loading}>
                <Search className="h-4 w-4 mr-1" />
                {loading ? "Loading..." : "Search"}
              </Button>
            </form>
          </div>

          <div className="flex-1 bg-gradient-to-br from-slate-950 to-slate-900 relative">
            {view === "graph" ? (
              <>
                {error && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <p className="text-sm text-destructive">{error}</p>
                  </div>
                )}
                {!data && !loading && !error && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="text-center text-muted-foreground">
                      <Network className="h-12 w-12 mx-auto mb-3 opacity-50" />
                      <p className="text-sm font-medium">Enter an entity to visualize</p>
                      <p className="text-xs mt-1">Phone number, UPI ID, AnyDesk ID, or URL</p>
                    </div>
                  </div>
                )}
                {data && (
                  <GraphCanvas
                    data={data}
                    onNodeClick={handleNodeClick}
                    onExpand={handleExpand}
                    depth={depth}
                  />
                )}
              </>
            ) : (
              <div className="p-4">
                <RingsList
                  onSelectRing={(ringId) => {
                    setView("graph")
                    setSearchQuery(ringId)
                    setEntityType("PHONE")
                    fetchNeighborhood(ringId, "PHONE", 2)
                  }}
                />
              </div>
            )}
          </div>
        </div>

        {selectedNode && data && (
          <div className="w-72 border-l p-3">
            <NodeDetailPanel
              node={selectedNode}
              data={data}
              onClose={() => setSelectedNode(null)}
            />
          </div>
        )}
      </div>
    </div>
  )
}
