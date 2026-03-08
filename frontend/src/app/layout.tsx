import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import Navbar from "@/components/Navbar";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: {
    default: "Ringside Analytics",
    template: "%s | Ringside Analytics",
  },
  description:
    "40+ years of pro wrestling data — match history, career stats, and ML-powered predictions across WWE, AEW, WCW, ECW, and TNA.",
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000"),
  openGraph: {
    type: "website",
    siteName: "Ringside Analytics",
    title: "Ringside Analytics",
    description:
      "40+ years of pro wrestling data — match history, career stats, and ML-powered predictions.",
  },
  twitter: {
    card: "summary_large_image",
    title: "Ringside Analytics",
    description:
      "40+ years of pro wrestling data — match history, career stats, and ML-powered predictions.",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-zinc-950 text-zinc-100 min-h-screen`}
      >
        <Navbar />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
