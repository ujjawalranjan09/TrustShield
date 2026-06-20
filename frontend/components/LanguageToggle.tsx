"use client"

import React from "react"
import { useLocale } from "next-intl"
import { useRouter, usePathname } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Globe } from "lucide-react"

export default function LanguageToggle() {
  const locale = useLocale()
  const router = useRouter()
  const pathname = usePathname()

  const toggleLocale = () => {
    const newLocale = locale === "en" ? "hi" : "en"
    const segments = pathname.split("/")
    segments[1] = newLocale
    router.push(segments.join("/"))
    document.cookie = `NEXT_LOCALE=${newLocale};path=/;max-age=31536000`
  }

  return (
    <Button variant="ghost" size="sm" onClick={toggleLocale} className="gap-1.5 text-xs font-medium">
      <Globe className="h-3.5 w-3.5" />
      {locale === "en" ? "EN" : "HI"}
    </Button>
  )
}
