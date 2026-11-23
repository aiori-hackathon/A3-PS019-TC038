"use client";

import { Suspense, type ReactNode } from "react";
import { AppProvider } from "@/components/app-context";
import { ServerGate } from "@/components/gate";
import { AppShell } from "@/components/shell";
import { SkeletonPage } from "@/components/ui";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AppProvider>
      <ServerGate>
        <Suspense fallback={<div className="content"><SkeletonPage /></div>}>
          <AppShell>{children}</AppShell>
        </Suspense>
      </ServerGate>
    </AppProvider>
  );
}
