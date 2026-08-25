import type { Metadata } from "next";
import { JetBrains_Mono, IBM_Plex_Mono, Space_Mono } from "next/font/google";
import "./globals.css";

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-ibm-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const spaceMono = Space_Mono({
  variable: "--font-space-mono",
  subsets: ["latin"],
  weight: ["400", "700"],
});

export const metadata: Metadata = {
  title: "Groundwork",
  description: "Verify what your codebase actually does. Grounded architecture analysis for any public GitHub repository.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${jetbrainsMono.variable} ${ibmPlexMono.variable} ${spaceMono.variable} h-full antialiased font-jetbrains bg-[#0d1117] text-[#c9d1d9]`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
