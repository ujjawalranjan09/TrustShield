import Link from 'next/link';

export default function Home() {
  return (
    <div className="min-h-screen bg-[#0b0f1a] flex flex-col items-center justify-center">
      <div className="text-center space-y-8 px-4">
        <div className="flex items-center justify-center gap-3">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-info/20 text-info">
            <svg className="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <h1 className="text-4xl font-bold text-white tracking-tight">TrustShield</h1>
        </div>
        
        <p className="text-lg text-slate-400 max-w-2xl mx-auto">
          Real-time AI-powered fraud detection platform for UPI and digital payments in India.
          Protecting 500M+ UPI users from scams, vishing, and financial fraud.
        </p>
        
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center px-6 py-3 rounded-lg bg-info text-white font-medium hover:bg-info/90 transition-colors"
          >
            <svg className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            View Dashboard
          </Link>
          <Link
            href="/scan"
            className="inline-flex items-center justify-center px-6 py-3 rounded-lg bg-success text-white font-medium hover:bg-success/90 transition-colors"
          >
            <svg className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
            </svg>
            Scan a Message
          </Link>
          <Link
            href="/lookup"
            className="inline-flex items-center justify-center px-6 py-3 rounded-lg bg-surface-light text-slate-300 font-medium hover:bg-surface-lighter transition-colors border border-surface-light"
          >
            <svg className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            Lookup Entity
          </Link>
        </div>
        
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mt-12 max-w-4xl mx-auto">
          <div className="bg-surface rounded-xl p-6 border border-surface-light">
            <div className="text-3xl font-bold text-info mb-2">&lt;300ms</div>
            <div className="text-sm text-slate-400">Analysis Response Time</div>
          </div>
          <div className="bg-surface rounded-xl p-6 border border-surface-light">
            <div className="text-3xl font-bold text-success mb-2">99.9%</div>
            <div className="text-sm text-slate-400">Uptime SLA</div>
          </div>
          <div className="bg-surface rounded-xl p-6 border border-surface-light">
            <div className="text-3xl font-bold text-warning mb-2">12+</div>
            <div className="text-sm text-slate-400">Languages Supported</div>
          </div>
        </div>

        <div className="mt-12 max-w-4xl mx-auto">
          <h2 className="text-xl font-bold text-white mb-6">Platform Features</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <Link href="/scan" className="bg-surface rounded-xl p-4 border border-surface-light hover:border-info/30 transition-colors text-left">
              <div className="text-sm font-semibold text-white mb-1">WhatsApp/Telegram Scanner</div>
              <div className="text-xs text-slate-400">Forward suspicious messages for instant analysis</div>
            </Link>
            <Link href="/lookup" className="bg-surface rounded-xl p-4 border border-surface-light hover:border-info/30 transition-colors text-left">
              <div className="text-sm font-semibold text-white mb-1">Community Scammer Database</div>
              <div className="text-xs text-slate-400">Check phone numbers, UPI IDs, and URLs</div>
            </Link>
            <Link href="/dashboard/explainability" className="bg-surface rounded-xl p-4 border border-surface-light hover:border-info/30 transition-colors text-left">
              <div className="text-sm font-semibold text-white mb-1">Explainability Dashboard</div>
              <div className="text-xs text-slate-400">Understand why decisions are made</div>
            </Link>
            <div className="bg-surface rounded-xl p-4 border border-surface-light">
              <div className="text-sm font-semibold text-white mb-1">QR Code Analysis</div>
              <div className="text-xs text-slate-400">Detect malicious QR codes and fake screenshots</div>
            </div>
            <div className="bg-surface rounded-xl p-4 border border-surface-light">
              <div className="text-sm font-semibold text-white mb-1">Behavioral Biometrics</div>
              <div className="text-xs text-slate-400">Detect coached victims via interaction patterns</div>
            </div>
            <div className="bg-surface rounded-xl p-4 border border-surface-light">
              <div className="text-sm font-semibold text-white mb-1">Predictive Hotspot Map</div>
              <div className="text-xs text-slate-400">Geographic fraud trend visualization</div>
            </div>
            <div className="bg-surface rounded-xl p-4 border border-surface-light">
              <div className="text-sm font-semibold text-white mb-1">Multi-Bank Intelligence</div>
              <div className="text-xs text-slate-400">Privacy-preserving cross-bank fraud sharing</div>
            </div>
            <div className="bg-surface rounded-xl p-4 border border-surface-light">
              <div className="text-sm font-semibold text-white mb-1">Voice Call Analysis</div>
              <div className="text-xs text-slate-400">Real-time vishing detection via WebSocket</div>
            </div>
            <div className="bg-surface rounded-xl p-4 border border-surface-light">
              <div className="text-sm font-semibold text-white mb-1">Victim Recovery</div>
              <div className="text-xs text-slate-400">Step-by-step recovery with auto-complaint drafts</div>
            </div>
            <div className="bg-surface rounded-xl p-4 border border-surface-light">
              <div className="text-sm font-semibold text-white mb-1">Web + iOS SDKs</div>
              <div className="text-xs text-slate-400">Ready-to-use client libraries</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
