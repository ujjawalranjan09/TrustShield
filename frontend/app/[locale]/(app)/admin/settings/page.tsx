"use client"

import React, { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { useAuth } from "@/lib/auth"
import { Settings, Shield, Bell, Key, User } from "lucide-react"

export default function AdminSettingsPage() {
  const { user } = useAuth()
  const [saved, setSaved] = useState(false)

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Settings className="h-5 w-5" /> Settings
        </h1>
        <p className="text-sm text-muted-foreground">Manage your account and platform settings</p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm flex items-center gap-2"><User className="h-4 w-4" /> Profile</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleSave} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Full Name</Label>
                <Input defaultValue={user?.full_name || ""} />
              </div>
              <div className="space-y-2">
                <Label>Email</Label>
                <Input defaultValue={user?.email || ""} disabled />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Badge variant="secondary">{user?.role || "analyst"}</Badge>
            </div>
            <Button type="submit">{saved ? "Saved!" : "Save Changes"}</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm flex items-center gap-2"><Key className="h-4 w-4" /> Change Password</CardTitle></CardHeader>
        <CardContent>
          <form className="space-y-4">
            <div className="space-y-2">
              <Label>Current Password</Label>
              <Input type="password" />
            </div>
            <div className="space-y-2">
              <Label>New Password</Label>
              <Input type="password" />
            </div>
            <div className="space-y-2">
              <Label>Confirm New Password</Label>
              <Input type="password" />
            </div>
            <Button variant="outline">Update Password</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm flex items-center gap-2"><Bell className="h-4 w-4" /> Notifications</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
            <div>
              <p className="text-sm font-medium">Fraud Alerts</p>
              <p className="text-xs text-muted-foreground">Get notified for high-risk detections</p>
            </div>
            <input type="checkbox" defaultChecked className="h-4 w-4" />
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
            <div>
              <p className="text-sm font-medium">Intervention Updates</p>
              <p className="text-xs text-muted-foreground">Status changes on interventions</p>
            </div>
            <input type="checkbox" defaultChecked className="h-4 w-4" />
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
            <div>
              <p className="text-sm font-medium">Weekly Reports</p>
              <p className="text-xs text-muted-foreground">Summary of fraud trends</p>
            </div>
            <input type="checkbox" className="h-4 w-4" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-sm flex items-center gap-2"><Shield className="h-4 w-4" /> Security</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
            <div>
              <p className="text-sm font-medium">Two-Factor Authentication</p>
              <p className="text-xs text-muted-foreground">Add an extra layer of security</p>
            </div>
            <Button variant="outline" size="sm">Enable 2FA</Button>
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
            <div>
              <p className="text-sm font-medium">Active Sessions</p>
              <p className="text-xs text-muted-foreground">Manage your active login sessions</p>
            </div>
            <Button variant="outline" size="sm">View Sessions</Button>
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
            <div>
              <p className="text-sm font-medium">API Keys</p>
              <p className="text-xs text-muted-foreground">Manage your API keys</p>
            </div>
            <Button variant="outline" size="sm">Manage Keys</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
