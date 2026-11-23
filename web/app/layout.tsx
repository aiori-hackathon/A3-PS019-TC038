import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

const SITE = process.env.NEXT_PUBLIC_SITE_URL || "https://privacytwin.vercel.app";
const DESCRIPTION =
  "PrivacyTwin mirrors your organisation's personal-data estate: discover where personal data lives, rewind it over time, simulate exposure, prove detection accuracy and export hash-verified evidence. Evidence, not verdicts.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: { default: "PrivacyTwin: your personal-data estate, mirrored", template: "%s · PrivacyTwin" },
  description: DESCRIPTION,
  applicationName: "PrivacyTwin",
  icons: { icon: "/favicon.svg" },
  openGraph: {
    type: "website",
    title: "PrivacyTwin: your personal-data estate, mirrored",
    description: DESCRIPTION,
    siteName: "PrivacyTwin",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "PrivacyTwin: a digital twin of your personal-data estate" }],
  },
  twitter: { card: "summary_large_image", title: "PrivacyTwin", description: DESCRIPTION, images: ["/og.png"] },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0b0f14" },
    { media: "(prefers-color-scheme: light)", color: "#f5f7fa" },
  ],
};

// Runs before paint: saved choice, else the system setting, else dark.
const THEME_SCRIPT = `try{var t=localStorage.getItem('pt.theme');if(!t){t=window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'}document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme='dark'}`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
