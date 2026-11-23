"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { SkeletonPage } from "@/components/ui";
import { storage } from "@/lib/api";

/** Session continuity: reopen the last page, otherwise the overview. */
export default function AppIndex() {
  const router = useRouter();
  useEffect(() => {
    const last = storage.get("pt.lastPage");
    router.replace(last && last.startsWith("/app/") && last !== "/app/" ? last : "/app/overview/");
  }, [router]);
  return <SkeletonPage />;
}
