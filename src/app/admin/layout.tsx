'use client'

import { SidebarProvider, Sidebar, SidebarContent, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'
import { LayoutDashboard, Package, ShoppingCart, Users, Settings, LogOut } from 'lucide-react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from "react";
import { LoginForm } from "@/components/LoginForm";

const sidebarItems = [
  {
    title: 'Dashboard',
    icon: LayoutDashboard,
    href: '/admin',
  },
  {
    title: 'Products',
    icon: Package,
    href: '/admin/products',
  },
  {
    title: 'Orders',
    icon: ShoppingCart,
    href: '/admin/orders',
  },
  {
    title: 'Customers',
    icon: Users,
    href: '/admin/customers',
  },
  {
    title: 'Settings',
    icon: Settings,
    href: '/admin/settings',
  },
]

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()
  const router = useRouter()
  const [isLoggedIn, setIsLoggedIn] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Check if user is logged in from localStorage
    const adminAuth = localStorage.getItem('adminAuth')
    if (adminAuth === 'true') {
      setIsLoggedIn(true)
    }
    setIsLoading(false)
  }, [])

  const handleLogin = () => {
    // Store authentication state in localStorage for persistence
    localStorage.setItem('adminAuth', 'true')
    setIsLoggedIn(true)
  }

  const handleLogout = () => {
    localStorage.removeItem('adminAuth')
    setIsLoggedIn(false)
  }

  // Show loading state while checking authentication
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
      </div>
    )
  }

  // Show login form if not logged in
  if (!isLoggedIn) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <LoginForm onLogin={handleLogin} />
      </div>
    )
  }
  
  return (
    <div className="h-screen flex flex-col">
      <SidebarProvider>
        <div className="flex flex-col md:flex-row flex-1 overflow-hidden">
          <Sidebar className="w-full md:w-64 md:shrink-0 h-auto md:h-full border-r">
            <SidebarHeader>
              <div className="flex items-center justify-between gap-2 font-semibold p-4">
                <Link href="/admin" className="flex items-center gap-2">
                  <Package className="h-6 w-6" />
                  <span>Meo Stationery Admin</span>
                </Link>
              </div>
            </SidebarHeader>
            <SidebarContent>
              <SidebarGroup>
                <SidebarGroupLabel>Menu</SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {sidebarItems.map((item) => (
                      <SidebarMenuItem key={item.href}>
                        <SidebarMenuButton 
                          asChild
                          isActive={pathname === item.href}
                        >
                          <Link href={item.href} className="flex items-center gap-2 px-4 py-2">
                            <item.icon className="h-4 w-4" />
                            <span>{item.title}</span>
                          </Link>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    ))}
                    <SidebarMenuItem>
                      <SidebarMenuButton 
                        asChild
                        onClick={handleLogout}
                      >
                        <button className="flex items-center gap-2 px-4 py-2 w-full text-left text-red-500 hover:bg-red-50 rounded-md">
                          <LogOut className="h-4 w-4" />
                          <span>Logout</span>
                        </button>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            </SidebarContent>
          </Sidebar>
          <main className="flex-1 overflow-y-auto p-4 md:p-8 w-full">
            {children}
          </main>
        </div>
      </SidebarProvider>
    </div>
  )
}
