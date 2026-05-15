"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

export function TraceAutoRefresh({
  enabled,
  intervalMs = 2000,
  maxRefreshCount = 10,
}: {
  enabled: boolean;
  intervalMs?: number;
  maxRefreshCount?: number;
}) {
  const router = useRouter();
  const refreshCountRef = useRef(0);

  useEffect(() => {
    if (!enabled) {
      refreshCountRef.current = 0;
      return;
    }

    const timer = window.setInterval(() => {
      if (refreshCountRef.current >= maxRefreshCount) {
        window.clearInterval(timer);
        return;
      }
      refreshCountRef.current += 1;
      router.refresh();
    }, intervalMs);

    return () => window.clearInterval(timer);
  }, [enabled, intervalMs, maxRefreshCount, router]);

  return null;
}
