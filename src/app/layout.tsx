import './globals.css'
import { Quicksand } from 'next/font/google'
import React from "react";
import {Toaster} from "sonner";
import {Metadata} from "next";
import MainLayout from '../components/MainLayout';

const inter = Quicksand({ subsets: ['latin'] })

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
      <body className={`${inter.className} min-h-screen flex flex-col`}>
        <MainLayout>
          {children}
        </MainLayout>
        <Toaster richColors position="bottom-right" />
      </body>
    </html>
  )
}
