'use client'

import { usePathname } from 'next/navigation'

export function AdminRouteDetector({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isAdminRoute = pathname.startsWith('/admin')

  return (
    <>
      {!isAdminRoute && children}
    </>
  )
}
