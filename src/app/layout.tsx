import './globals.css'
import { Quicksand } from 'next/font/google'
import React from "react";
import {Toaster} from "sonner";
import {Metadata} from "next";
import MainLayout from '../components/MainLayout';

const inter = Quicksand({ subsets: ['latin'] })

// Nền theo version (build với NEXT_PUBLIC_APP_VERSION=3.0.x)
const VERSION_BG: Record<string, string> = {
  '3.0.1': 'bg-red-100',
  'v3.0.1': 'bg-red-100',
  '3.0.2': 'bg-green-100',
  'v3.0.2': 'bg-green-100',
  '3.0.3': 'bg-yellow-100',
  'v3.0.3': 'bg-yellow-100',
}
function getVersionBg(): string {
  const v = process.env.NEXT_PUBLIC_APP_VERSION || ''
  return VERSION_BG[v] ?? 'bg-background'
}

export const metadata: Metadata = {
  title: 'Meo Stationery',
  description: 'Your one-stop shop for all stationery needs',
  keywords: ['stationery', 'văn phòng phẩm', 'dụng cụ học tập'],
  openGraph: {
    title: 'Meo Stationery',
    description: 'Quality stationery products for everyone',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} min-h-screen flex flex-col ${getVersionBg()}`}>
        <MainLayout>
          {children}
        </MainLayout>
        <Toaster richColors position="bottom-right" />
      </body>
    </html>
  )
}
