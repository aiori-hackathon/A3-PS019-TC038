import Link from "next/link";
import { SitePage } from "@/components/site";

export default function NotFound() {
  return (
    <SitePage eyebrow="404" title="This page isn't in the twin" lede="The link may be old, or the page moved.">
      <div className="row wrap">
        <Link className="btn primary" href="/">Home</Link>
        <Link className="btn" href="/app/overview/">Open the app</Link>
      </div>
    </SitePage>
  );
}
