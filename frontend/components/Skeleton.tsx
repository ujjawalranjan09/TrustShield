'use client';

import React from 'react';

export function StatCardSkeleton() {
  return (
    <div className="bg-surface rounded-xl p-4 border border-surface-light animate-pulse">
      <div className="flex items-center gap-3 mb-3">
        <div className="h-10 w-10 rounded-lg bg-surface-light" />
        <div className="flex-1">
          <div className="h-3 w-20 bg-surface-light rounded mb-2" />
          <div className="h-5 w-16 bg-surface-light rounded" />
        </div>
      </div>
      <div className="h-3 w-24 bg-surface-light rounded" />
    </div>
  );
}

export function ChartSkeleton() {
  return (
    <div className="bg-surface rounded-xl p-6 border border-surface-light animate-pulse">
      <div className="h-5 w-32 bg-surface-light rounded mb-4" />
      <div className="h-48 bg-surface-light rounded" />
    </div>
  );
}

export function FeedSkeleton() {
  return (
    <div className="bg-surface rounded-xl p-4 border border-surface-light animate-pulse">
      <div className="h-5 w-32 bg-surface-light rounded mb-4" />
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-start gap-3 p-3 bg-surface-light/50 rounded-lg">
            <div className="h-8 w-8 rounded-full bg-surface-light" />
            <div className="flex-1">
              <div className="h-3 w-24 bg-surface-light rounded mb-2" />
              <div className="h-3 w-full bg-surface-light rounded" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
