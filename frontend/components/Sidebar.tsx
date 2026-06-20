"use client"

import React, { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard, Search, ScanLine, Network, HeartHandshake,
  Brain, Shield, Settings, ChevronDown, ChevronRight,
  MessageSquare, Map, FileText, Users, Activity
} from "lucide-react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"

interface NavItem {
  label: string
  labelHi: string
  href: string
  icon: React.ComponentType<{ className?: string }>
  children?: { label: string; labelHi: string; href: string }[]
}

const NAV_ITEMS: NavItem[] = [
  { label: "Overview", labelHi: "ओवरव्यू", href: "/dashboard", icon: LayoutDashboard },
  {
    label: "Investigate", labelHi: "जांच", href: "/investigate/sessions", icon: Search,
    children: [
      { label: "Sessions", labelHi: "सत्र", href: "/investigate/sessions" },
      { label: "Entity Lookup", labelHi: "एंटिटी लुकअप", href: "/investigate/lookup" },
      { label: "Graph Explorer", labelHi: "ग्राफ एक्सप्लोरर", href: "/investigate/graph" },
    ],
  },
  {
    label: "Scan", labelHi: "स्कैन", href: "/scan", icon: ScanLine,
    children: [
      { label: "Message Scanner", labelHi: "संदेश स्कैनर", href: "/scan" },
      { label: "Voice Monitor", labelHi: "वॉयस मॉनिटर", href: "/scan/voice" },
      { label: "Image / QR", labelHi: "इमेज / QR", href: "/scan/image" },
    ],
  },
  {
    label: "Intelligence", labelHi: "इंटेलिजेंस", href: "/intelligence/network", icon: Network,
    children: [
      { label: "Cross-Bank Network", labelHi: "क्रॉस-बैंक नेटवर्क", href: "/intelligence/network" },
      { label: "Hotspots Map", labelHi: "हॉटस्पॉट मैप", href: "/intelligence/hotspots" },
    ],
  },
  { label: "Recovery", labelHi: "रिकवरी", href: "/recovery", icon: HeartHandshake },
  { label: "Explainability", labelHi: "स्पष्टीकरण", href: "/dashboard/explainability", icon: Brain },
  { label: "Compliance", labelHi: "अनुपालन", href: "/compliance", icon: Shield },
  { label: "Admin", labelHi: "एडमिन", href: "/admin", icon: Settings },
]

export default function Sidebar() {
  const pathname = usePathname()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const toggleSection = (label: string) => {
    setExpanded(prev => ({ ...prev, [label]: !prev[label] }))
  }

  return (
    <aside className="hidden md:flex md:w-64 md:flex-col md:fixed md:inset-y-0 border-r border-border bg-card">
      <div className="flex h-14 items-center gap-2 px-4 border-b border-border">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/20 text-primary">
          <Shield className="h-4 w-4" />
        </div>
        <span className="font-semibold text-sm">TrustShield</span>
      </div>
      <ScrollArea className="flex-1 py-2">
        <nav className="space-y-1 px-2">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const isActive = pathname.startsWith(item.href)
            const hasChildren = item.children && item.children.length > 0
            const isExpanded = expanded[item.label] ?? isActive

            if (hasChildren) {
              return (
                <div key={item.label}>
                  <button
                    onClick={() => toggleSection(item.label)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="flex-1 text-left">{item.label}</span>
                    {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  </button>
                  {isExpanded && (
                    <div className="ml-4 mt-1 space-y-1">
                      {item.children!.map((child) => (
                        <Link
                          key={child.href}
                          href={child.href}
                          className={cn(
                            "flex items-center gap-3 rounded-lg px-3 py-1.5 text-sm transition-colors",
                            pathname === child.href
                              ? "bg-primary/10 text-primary font-medium"
                              : "text-muted-foreground hover:bg-muted hover:text-foreground"
                          )}
                        >
                          {child.label}
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              )
            }

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {item.label}
              </Link>
            )
          })}
        </nav>
      </ScrollArea>
    </aside>
  )
}
