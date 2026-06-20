"use client"

import React, { useState, useRef } from "react"
import { useMutation } from "@tanstack/react-query"
import Link from "next/link"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Loader2, ShieldAlert, ShieldCheck, MessageSquare, Mic, Image as ImageIcon, HelpCircle } from "lucide-react"
import { apiClient } from "@/lib/api"

interface VerdictResult {
  session_id: string
  is_scam: boolean
  scam_type: string
  risk_score: number
  risk_level: string
  confidence: number
  recommended_action: string
  entities: Array<{ entity_type: string; value: string; confidence_score: number }>
  modality: string
  created_at: string
}

interface TextScanResult {
  result: {
    is_scam: boolean
    confidence: number
    scam_type: string
    risk_level: string
    risk_score: number
    flagged_entities: Array<{ entity_type: string; value: string; confidence_score: number }>
    recommendation: string
    processing_time_ms: number
  }
  session_id: string
}

interface VoiceResult {
  is_scam: boolean
  confidence: number
  scam_type: string
  risk_score: number
  risk_level: string
  flagged_entities: Array<{ entity_type: string; value: string; confidence_score: number }>
  processing_time_ms: number
  verdict: VerdictResult | null
}

interface ImageResult {
  result: {
    has_qr_code: boolean
    qr_codes: Array<{ content: string; content_type: string; is_suspicious: boolean; risk_reasons: string[] }>
    has_suspicious_content: boolean
    image_hash: string
    analysis_notes: string[]
    risk_level: string
  }
  processing_time_ms: number
  verdict: VerdictResult | null
}

type Tab = "text" | "voice" | "image"

const SAMPLE_MESSAGES = [
  { label: "OTP Scam", text: "Hello sir, I am calling from bank. aapka debit card block ho gaya hai. Please share your OTP verify karne ke liye." },
  { label: "AnyDesk Scam", text: "Aapko refund process karne ke liye ek baar screen share karo. AnyDesk app download kijiye aur code bataiye: 123456789." },
  { label: "Legitimate", text: "Hi, when will my order be delivered? Your order will be delivered by tomorrow 8 PM." },
]

function getRiskBadgeVariant(level: string) {
  switch (level) {
    case "CRITICAL": return "destructive"
    case "HIGH": return "warning"
    case "MEDIUM": return "info"
    default: return "success"
  }
}

function VerdictCard({ verdict, sessionId }: { verdict: VerdictResult; sessionId?: string }) {
  const maskedEntities = verdict.entities.map((e) => ({
    ...e,
    value: e.value.length > 8 ? e.value.slice(0, 4) + "****" + e.value.slice(-3) : e.value,
  }))

  return (
    <div className="space-y-4">
      <Card className={verdict.risk_score >= 70 ? "border-destructive/20 bg-destructive/5" : verdict.risk_score >= 40 ? "border-warning/20 bg-warning/5" : "border-success/20 bg-success/5"}>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              {verdict.is_scam ? (
                <><ShieldAlert className="h-5 w-5" /> Scam Detected</>
              ) : (
                <><ShieldCheck className="h-5 w-5" /> Appears Safe</>
              )}
            </CardTitle>
            <div className="text-right">
              <div className="text-3xl font-bold">{verdict.risk_score}</div>
              <div className="text-xs text-muted-foreground">/ 100</div>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Risk Level</p>
              <Badge variant={getRiskBadgeVariant(verdict.risk_level) as any}>{verdict.risk_level}</Badge>
            </div>
            <div>
              <p className="text-muted-foreground">Confidence</p>
              <p className="font-medium">{(verdict.confidence * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-muted-foreground">Scam Type</p>
              <p className="font-medium">{verdict.scam_type.replace(/_/g, " ")}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Modality</p>
              <p className="font-medium">{verdict.modality}</p>
            </div>
          </div>
          <div className="mt-3">
            <p className="text-muted-foreground text-sm">Recommended Action</p>
            <p className="font-medium text-sm">{verdict.recommended_action.replace(/_/g, " ")}</p>
          </div>
        </CardContent>
      </Card>

      {maskedEntities.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Entities (masked)</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {maskedEntities.map((entity, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                  <div>
                    <p className="text-sm font-medium">{entity.value}</p>
                    <p className="text-xs text-muted-foreground">{entity.entity_type}</p>
                  </div>
                  <span className="text-xs text-muted-foreground">{(entity.confidence_score * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {sessionId && (
        <Link href={`/explain/chat?session_id=${sessionId}`}>
          <Button variant="outline" size="sm" className="gap-2">
            <HelpCircle className="h-4 w-4" /> Why?
          </Button>
        </Link>
      )}
    </div>
  )
}

function TextTab() {
  const [message, setMessage] = useState("")
  const [result, setResult] = useState<TextScanResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    if (!message.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await apiClient.analyzeChat({
        messages: [{ sender: "user", text: message }],
        session_metadata: {
          client_app_id: "web",
          session_id: crypto.randomUUID(),
          contact_initiated_by: "user",
          is_during_active_upi_session: false,
          user_device_hash: "web-user",
        },
      })
      setResult({
        result: {
          is_scam: data.risk_score >= 50,
          confidence: 0.8,
          scam_type: data.flagged_entities.length > 0 ? "phishing" : "unknown",
          risk_level: data.risk_level,
          risk_score: data.risk_score,
          flagged_entities: data.flagged_entities,
          recommendation: data.recommended_action,
          processing_time_ms: 0,
        },
        session_id: data.session_id,
      })
    } catch (e: any) {
      setError(e?.message || "Scan failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={(e) => { e.preventDefault(); handleSubmit() }} className="space-y-4">
            <Textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Paste a message, SMS, or chat to check for scams..."
              rows={5}
              className="resize-none"
            />
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={loading || !message.trim()}>
                {loading ? <><Loader2 className="h-4 w-4 animate-spin" /> Analyzing...</> : "Scan Text"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <div>
        <p className="text-sm font-medium text-muted-foreground mb-3">Try a sample</p>
        <div className="flex flex-wrap gap-2">
          {SAMPLE_MESSAGES.map((sample, i) => (
            <Button key={i} variant="outline" size="sm" onClick={() => setMessage(sample.text)}>
              {sample.label}
            </Button>
          ))}
        </div>
      </div>

      {error && (
        <Card className="border-destructive/20 bg-destructive/5">
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {result && (
        <VerdictCard
          verdict={{
            session_id: result.session_id,
            is_scam: result.result.is_scam,
            scam_type: result.result.scam_type,
            risk_score: result.result.risk_score,
            risk_level: result.result.risk_level,
            confidence: result.result.confidence,
            recommended_action: result.result.recommendation,
            entities: result.result.flagged_entities.map((e) => ({ ...e, value: e.value })),
            modality: "TEXT",
            created_at: new Date().toISOString(),
          }}
          sessionId={result.session_id}
        />
      )}
    </div>
  )
}

function VoiceTab() {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<VoiceResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleSubmit = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append("file", file)
      const data = await apiClient.analyzeVoice(formData)
      setResult(data)
    } catch (e: any) {
      setError(e?.message?.includes("429") ? "Rate limit exceeded. Please wait a moment and try again." : e?.message || "Voice analysis failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-6">
          <div className="space-y-4">
            <div>
              <Input
                ref={fileRef}
                type="file"
                accept="audio/*"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="cursor-pointer"
              />
              <p className="text-xs text-muted-foreground mt-1">Upload an audio file (MP3, WAV, OGG)</p>
            </div>
            <Button onClick={handleSubmit} disabled={loading || !file}>
              {loading ? <><Loader2 className="h-4 w-4 animate-spin" /> Analyzing...</> : "Analyze Audio"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <Card className="border-destructive/20 bg-destructive/5">
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {result && result.verdict && (
        <VerdictCard verdict={result.verdict} sessionId={result.verdict.session_id} />
      )}

      {result && !result.verdict && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Voice Analysis Result</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Risk Score</p>
                <p className="font-medium">{result.risk_score}/100</p>
              </div>
              <div>
                <p className="text-muted-foreground">Risk Level</p>
                <Badge variant={getRiskBadgeVariant(result.risk_level) as any}>{result.risk_level}</Badge>
              </div>
              <div>
                <p className="text-muted-foreground">Scam Type</p>
                <p className="font-medium">{result.scam_type.replace(/_/g, " ")}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Processing</p>
                <p className="font-medium">{result.processing_time_ms}ms</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function ImageTab() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [result, setResult] = useState<ImageResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] || null
    setFile(f)
    if (f) {
      const reader = new FileReader()
      reader.onloadend = () => setPreview(reader.result as string)
      reader.readAsDataURL(f)
    } else {
      setPreview(null)
    }
  }

  const handleSubmit = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append("file", file)
      const data = await apiClient.analyzeImage(formData)
      setResult(data)
    } catch (e: any) {
      setError(e?.message?.includes("429") ? "Rate limit exceeded. Please wait a moment and try again." : e?.message || "Image analysis failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="pt-6">
          <div className="space-y-4">
            <div>
              <Input
                ref={fileRef}
                type="file"
                accept="image/*"
                onChange={handleFileChange}
                className="cursor-pointer"
              />
              <p className="text-xs text-muted-foreground mt-1">Upload an image or QR code (PNG, JPG, WEBP, max 10MB)</p>
            </div>
            {preview && (
              <div className="relative w-full max-w-xs">
                <img src={preview} alt="Preview" className="rounded-lg border max-h-48 object-contain" />
              </div>
            )}
            <Button onClick={handleSubmit} disabled={loading || !file}>
              {loading ? <><Loader2 className="h-4 w-4 animate-spin" /> Analyzing...</> : "Analyze Image"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <Card className="border-destructive/20 bg-destructive/5">
          <CardContent className="pt-6">
            <p className="text-sm text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {result && result.verdict && (
        <VerdictCard verdict={result.verdict} sessionId={result.verdict.session_id} />
      )}

      {result && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Image Details</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">QR Code Found</span>
                <span className="font-medium">{result.result.has_qr_code ? "Yes" : "No"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Suspicious Content</span>
                <span className="font-medium">{result.result.has_suspicious_content ? "Yes" : "No"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Risk Level</span>
                <Badge variant={getRiskBadgeVariant(result.result.risk_level.toUpperCase()) as any}>{result.result.risk_level}</Badge>
              </div>
              {result.result.qr_codes.length > 0 && (
                <div className="mt-3">
                  <p className="text-muted-foreground mb-2">QR Codes Detected</p>
                  {result.result.qr_codes.map((qr, i) => (
                    <div key={i} className="p-2 rounded bg-muted/50 mb-2">
                      <p className="text-xs font-mono break-all">{qr.content.slice(0, 100)}</p>
                      <p className="text-xs text-muted-foreground">{qr.content_type} {qr.is_suspicious ? "(suspicious)" : ""}</p>
                    </div>
                  ))}
                </div>
              )}
              {result.result.analysis_notes.length > 0 && (
                <div className="mt-3">
                  <p className="text-muted-foreground mb-2">Analysis Notes</p>
                  <ul className="list-disc list-inside text-xs text-muted-foreground space-y-1">
                    {result.result.analysis_notes.map((note, i) => (
                      <li key={i}>{note}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export default function AnalyzePage() {
  const [activeTab, setActiveTab] = useState<Tab>("text")

  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: "text", label: "Text", icon: <MessageSquare className="h-4 w-4" /> },
    { key: "voice", label: "Voice", icon: <Mic className="h-4 w-4" /> },
    { key: "image", label: "Image", icon: <ImageIcon className="h-4 w-4" /> },
  ]

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold">Analyze</h1>
        <p className="text-sm text-muted-foreground">Check text messages, voice calls, or images for scam indicators</p>
      </div>

      <div className="flex border-b">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.key
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "text" && <TextTab />}
      {activeTab === "voice" && <VoiceTab />}
      {activeTab === "image" && <ImageTab />}
    </div>
  )
}
