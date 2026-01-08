'use client'

import Navbar from '@/components/Navbar'
import Footer from '@/components/Footer'
import React from "react"
import { usePathname } from 'next/navigation'

export default function MainLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const isAdminRoute = pathname.startsWith('/admin')

  // Don't render Navbar and Footer on admin routes
  if (isAdminRoute) {
    return <>{children}</>
  }

  return (
    <>
      <Navbar />
      <main className="container mx-auto px-4 py-8 flex-grow">
        {children}
      </main>
      <Footer />
    </>
  )
}
