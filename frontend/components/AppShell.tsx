"use client"

import React from "react"
import Sidebar from "@/components/Sidebar"
import LanguageToggle from "@/components/LanguageToggle"
import ThemeToggle from "@/components/ThemeToggle"
import { Bell, User } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import Link from "next/link"

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <div className="md:pl-64">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-4 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-6">
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <LanguageToggle />
            <ThemeToggle />
            <Button variant="ghost" size="icon" className="relative">
              <Bell className="h-4 w-4" />
              <span className="absolute -top-0.5 -right-0.5 h-3.5 w-3.5 rounded-full bg-destructive text-[10px] font-bold text-destructive-foreground flex items-center justify-center">
                3
              </span>
            </Button>
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
