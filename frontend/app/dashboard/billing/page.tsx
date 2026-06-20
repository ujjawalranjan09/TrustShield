"use client";

import React, { useEffect, useState } from 'react';
import { apiClient } from '../../../lib/api';
import { ErrorBoundary } from '../../../components/ErrorBoundary';
import StatCard from '../../../components/StatCard';

interface Usage {
  scan_calls: number;
  webhook_calls: number;
  scan_limit: number;
  webhook_limit: number;
  remaining_scan: number;
  remaining_webhook: number;
  percent_used: number;
  bucket: string;
}

interface Plan {
  code: string;
  name: string;
  monthly_scan_limit: number;
  monthly_webhook_limit: number;
  sla_percent: number;
}

interface Subscription {
  plan_code: string;
  status: string;
  current_period_end: string | null;
  stripe_customer_id: string | null;
}

function UsageSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-8 w-48 bg-surface-lighter rounded" />
      <div className="h-4 w-96 bg-surface-lighter rounded" />
      <div className="h-24 bg-surface-lighter rounded" />
      <div className="h-24 bg-surface-lighter rounded" />
    </div>
  );
}

function BillingContent() {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [usageData, subData, plansData] = await Promise.all([
          apiClient.getUsage(),
          apiClient.getSubscription(),
          apiClient.getPlans(),
        ]);
        setUsage(usageData);
        setSubscription(subData);
        setPlans(plansData);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Failed to load billing data';
        setError(msg);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  const handleManageSubscription = async () => {
    setPortalLoading(true);
    try {
      const result = await apiClient.createPortal();
      window.location.href = result.url;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to open portal';
      setError(msg);
    } finally {
      setPortalLoading(false);
    }
  };

  const handleUpgrade = async (priceId: string) => {
    try {
      const successUrl = `${window.location.origin}/dashboard/billing?success=true`;
      const cancelUrl = `${window.location.origin}/dashboard/billing?canceled=true`;
      const result = await apiClient.createCheckout(priceId, successUrl, cancelUrl);
      window.location.href = result.url;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create checkout';
      setError(msg);
    }
  };

  if (loading) return <UsageSkeleton />;

  if (error) {
    return (
      <div className="rounded-lg bg-danger/10 border border-danger/20 p-6 text-center">
        <p className="text-danger font-medium">{error}</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 px-4 py-2 bg-info/20 text-info rounded-lg hover:bg-info/30 transition-colors text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  const planNames: Record<string, string> = {
    free: 'Free',
    pro: 'Pro',
    bank: 'Bank',
    enterprise: 'Enterprise',
  };

  const planColors: Record<string, string> = {
    free: 'text-slate-400',
    pro: 'text-accent-purple',
    bank: 'text-info',
    enterprise: 'text-warning',
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white">Billing & Usage</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Monitor your API usage and manage your subscription plan
        </p>
      </div>

      {/* Current Plan Card */}
      <div className="rounded-xl bg-surface border border-surface-light p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm text-slate-500">Current Plan</p>
            <h3 className={`text-xl font-bold mt-0.5 ${planColors[subscription?.plan_code || 'free'] || 'text-white'}`}>
              {planNames[subscription?.plan_code || 'free'] || 'Free'}
            </h3>
          </div>
          <div className="text-right">
            <p className="text-sm text-slate-500">Status</p>
            <span className={`inline-block mt-0.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${
              subscription?.status === 'active'
                ? 'bg-success/10 text-success border border-success/20'
                : subscription?.status === 'past_due'
                ? 'bg-warning/10 text-warning border border-warning/20'
                : 'bg-slate-500/10 text-slate-400 border border-slate-500/20'
            }`}>
              {subscription?.status || 'active'}
            </span>
          </div>
        </div>
        {subscription?.current_period_end && (
          <p className="text-xs text-slate-500">
            Current period ends: {new Date(subscription.current_period_end).toLocaleDateString('en-IN', {
              year: 'numeric', month: 'long', day: 'numeric',
            })}
          </p>
        )}
        <div className="mt-4 flex gap-3">
          {subscription?.stripe_customer_id ? (
            <button
              onClick={handleManageSubscription}
              disabled={portalLoading}
              className="px-4 py-2 bg-info/20 text-info rounded-lg hover:bg-info/30 transition-colors text-sm font-medium disabled:opacity-50"
            >
              {portalLoading ? 'Opening...' : 'Manage Subscription'}
            </button>
          ) : (
            <span className="text-xs text-slate-500">No active Stripe subscription</span>
          )}
        </div>
      </div>

      {/* Usage Bars */}
      {usage && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <StatCard
            label="Scan API Calls"
            value={`${usage.scan_calls.toLocaleString('en-IN')} / ${usage.scan_limit === -1 ? '∞' : usage.scan_limit.toLocaleString('en-IN')}`}
            color={usage.remaining_scan === 0 ? 'red' : usage.remaining_scan < 100 ? 'orange' : 'blue'}
            icon={
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            }
          />
          <StatCard
            label="Webhook Calls"
            value={`${usage.webhook_calls.toLocaleString('en-IN')} / ${usage.webhook_limit === -1 ? '∞' : usage.webhook_limit.toLocaleString('en-IN')}`}
            color={usage.remaining_webhook === 0 ? 'red' : usage.remaining_webhook < 10 ? 'orange' : 'green'}
            icon={
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            }
          />
        </div>
      )}

      {/* Usage Progress Bar */}
      {usage && usage.scan_limit > 0 && (
        <div className="rounded-xl bg-surface border border-surface-light p-6">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-slate-500">Monthly Usage</p>
            <p className="text-sm font-medium text-white">{usage.percent_used.toFixed(1)}%</p>
          </div>
          <div className="h-3 bg-surface-lighter rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                usage.percent_used > 90
                  ? 'bg-danger'
                  : usage.percent_used > 70
                  ? 'bg-warning'
                  : 'bg-success'
              }`}
              style={{ width: `${Math.min(usage.percent_used, 100)}%` }}
            />
          </div>
          <div className="flex justify-between mt-2 text-xs text-slate-500">
            <span>0</span>
            <span>Month: {usage.bucket}</span>
            <span>{usage.scan_limit.toLocaleString('en-IN')}</span>
          </div>
          {usage.remaining_scan === 0 && (
            <div className="mt-3 p-3 rounded-lg bg-warning/10 border border-warning/20">
              <p className="text-sm text-warning font-medium">
                You have reached your monthly scan limit. Upgrade your plan to continue.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Plans */}
      <div>
        <h3 className="text-lg font-bold text-white mb-4">Available Plans</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {plans.map((plan) => {
            const isCurrent = plan.code === subscription?.plan_code;
            const isUnlimited = plan.monthly_scan_limit === -1;
            return (
              <div
                key={plan.code}
                className={`rounded-xl border p-6 ${
                  isCurrent
                    ? 'border-info/40 bg-info/5'
                    : 'border-surface-light bg-surface hover:border-surface-lighter transition-colors'
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <h4 className={`text-lg font-bold ${
                    plan.code === 'enterprise' ? 'text-warning' :
                    plan.code === 'bank' ? 'text-info' :
                    plan.code === 'pro' ? 'text-accent-purple' :
                    'text-white'
                  }`}>
                    {plan.name}
                  </h4>
                  {isCurrent && (
                    <span className="px-2 py-0.5 rounded-full bg-info/10 text-info text-xs font-medium border border-info/20">
                      Current
                    </span>
                  )}
                </div>
                <div className="space-y-2 text-sm">
                  <p className="text-slate-400">
                    <span className="text-white font-medium">
                      {isUnlimited ? 'Unlimited' : plan.monthly_scan_limit.toLocaleString('en-IN')}
                    </span>{' '}
                    scans/mo
                  </p>
                  <p className="text-slate-400">
                    <span className="text-white font-medium">
                      {isUnlimited ? 'Unlimited' : plan.monthly_webhook_limit.toLocaleString('en-IN')}
                    </span>{' '}
                    webhooks/mo
                  </p>
                  <p className="text-slate-400">
                    SLA: <span className="text-white font-medium">{plan.sla_percent}%</span>
                  </p>
                </div>
                {!isCurrent && plan.code !== 'enterprise' && (
                  <button
                    onClick={() => {
                      // For free -> pro/bank upgrades, get the price_id from the plan
                      const priceIds: Record<string, string> = {
                        pro: process.env.NEXT_PUBLIC_STRIPE_PRICE_PRO || '',
                        bank: process.env.NEXT_PUBLIC_STRIPE_PRICE_BANK || '',
                      };
                      if (priceIds[plan.code]) {
                        handleUpgrade(priceIds[plan.code]);
                      } else {
                        alert('Upgrade is handled via the Stripe Customer Portal');
                        handleManageSubscription();
                      }
                    }}
                    className="mt-4 w-full px-4 py-2 bg-info/20 text-info rounded-lg hover:bg-info/30 transition-colors text-sm font-medium"
                  >
                    Upgrade
                  </button>
                )}
                {plan.code === 'enterprise' && !isCurrent && (
                  <button
                    onClick={handleManageSubscription}
                    className="mt-4 w-full px-4 py-2 bg-warning/20 text-warning rounded-lg hover:bg-warning/30 transition-colors text-sm font-medium"
                  >
                    Contact Sales
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function BillingPage() {
  return (
    <div className="min-h-screen bg-[#0b0f1a]">
      <header className="border-b border-surface-light bg-surface/80 backdrop-blur-md sticky top-0 z-10">
        <div className="mx-auto max-w-[1200px] px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a href="/dashboard" className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
              <span className="text-sm">Dashboard</span>
            </a>
            <span className="text-slate-600">/</span>
            <span className="text-sm text-white font-medium">Billing</span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1200px] px-6 py-6">
        <ErrorBoundary>
          <BillingContent />
        </ErrorBoundary>
      </main>
    </div>
  );
}