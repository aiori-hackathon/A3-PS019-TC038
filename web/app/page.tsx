"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Loader3D } from "@/components/ui";

/** No marketing page: the root opens the tool directly. */
export default function Root() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/app/");
  }, [router]);
  return (
    <main className="gate">
      <noscript><a href="/app/overview/">Open PrivacyTwin</a></noscript>
      <Loader3D label="Opening PrivacyTwin…" />
    </main>
  );
}
