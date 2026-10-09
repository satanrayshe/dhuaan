import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Noto_Sans_Devanagari, Noto_Sans_Gurmukhi } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/dhuaan/providers";
import { TopBar } from "@/components/dhuaan/top-bar";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const notoDeva = Noto_Sans_Devanagari({
  variable: "--font-noto-deva",
  subsets: ["devanagari"],
  // loaded on demand via unicode-range; preloading every weight only drew "preloaded but not used" warnings
  preload: false,
  weight: ["400", "500", "600"],
});
const notoGuru = Noto_Sans_Gurmukhi({
  variable: "--font-noto-guru",
  subsets: ["gurmukhi"],
  // loaded on demand via unicode-range; preloading every weight only drew "preloaded but not used" warnings
  preload: false,
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: { default: "Dhuaan · ਧੂੰਆਂ · धुआँ", template: "%s · Dhuaan" },
  description:
    "See the smoke before it reaches you. A 72-hour farm-fire smoke forecast for every village, school and ward in North India.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0c0e" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en-IN"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} ${notoDeva.variable} ${notoGuru.variable} h-full antialiased`}
    >
      <body className="flex min-h-dvh flex-col">
        <Providers>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
          >
            Skip to content
          </a>
          <TopBar />
          <main id="main" className="flex min-h-0 flex-1 flex-col">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
