"use client"

import React, { useState } from "react"
import Sidebar from "@/components/Sidebar"
import LanguageToggle from "@/components/LanguageToggle"
import ThemeToggle from "@/components/ThemeToggle"
import { Bell, User, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import Link from "next/link"

const MOCK_NOTIFICATIONS = [
  { id: 1, title: "High-risk scam detected", desc: "OTP phishing attempt flagged at 92% confidence", time: "2 min ago", read: false },
  { id: 2, title: "Fraud ring identified", desc: "New 5-member ring detected across 3 banks", time: "15 min ago", read: false },
  { id: 3, title: "Intervention sent", desc: "WhatsApp warning delivered to victim +91****3210", time: "1 hour ago", read: false },
]

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [showNotifications, setShowNotifications] = useState(false)

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <div className="md:pl-64">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-4 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-6">
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <LanguageToggle />
            <ThemeToggle />
            <div className="relative">
              <Button variant="ghost" size="icon" className="relative" onClick={() => setShowNotifications(!showNotifications)}>
                <Bell className="h-4 w-4" />
                <span className="absolute -top-0.5 -right-0.5 h-3.5 w-3.5 rounded-full bg-destructive text-[10px] font-bold text-destructive-foreground flex items-center justify-center">
                  {MOCK_NOTIFICATIONS.filter(n => !n.read).length}
                </span>
              </Button>
              {showNotifications && (
                <div className="absolute right-0 top-10 w-80 bg-card border border-border rounded-lg shadow-lg z-50">
                  <div className="flex items-center justify-between p-3 border-b border-border">
                    <span className="text-sm font-semibold">Notifications</span>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setShowNotifications(false)}>
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                  <div className="max-h-80 overflow-y-auto">
                    {MOCK_NOTIFICATIONS.map(n => (
                      <div key={n.id} className={`p-3 border-b border-border hover:bg-muted/50 cursor-pointer ${!n.read ? "bg-primary/5" : ""}`}>
                        <p className="text-sm font-medium">{n.title}</p>
                        <p className="text-xs text-muted-foreground mt-1">{n.desc}</p>
                        <p className="text-xs text-muted-foreground mt-1">{n.time}</p>
                      </div>
                    ))}
                  </div>
                  <div className="p-2 text-center border-t border-border">
                    <Button variant="ghost" size="sm" className="text-xs">Mark all as read</Button>
                  </div>
                </div>
              )}
            </div>
            <Link href="/admin/settings">
              <Button variant="ghost" size="icon">
                <User className="h-4 w-4" />
              </Button>
            </Link>
          </div>
        </header>
        <main className="p-6">{children}</main>
      </div>
    </div>
  )
}
