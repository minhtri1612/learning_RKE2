import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const getStockStatus = (quantity: number) => {
  if (quantity === 0) return 'OUT_OF_STOCK'
  if (quantity < 20) return 'RUNNING_LOW'
  return 'IN_STOCK'
}

export const formatToVND = (price: number) => {
  return new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'VND',
    minimumFractionDigits: 0
  }).format(price)
}

export const calculateTotalRevenue = (orders: any[]) => {
  return orders
    .filter(order => order.status !== 'CANCELLED')
    .reduce((sum, order) => sum + (order.payment?.[0]?.amount || 0), 0)
}

export const generateChartData = (orders: any[]) => {
  const chartData = orders
    .filter(order => order.status !== 'CANCELLED')
    .reduce((acc, order) => {
      const month = new Date(order.createdAt).toLocaleString('default', { month: 'short' })
      const amount = order.payment[0]?.amount || 0
      acc[month] = (acc[month] || 0) + amount
      return acc
    }, {})

  return Object.entries(chartData).map(([name, total]) => ({
    name,
    total
  }))
}

export const getRecentSales = (orders: any[]) => {
  return orders
      .filter(order => order.status !== 'CANCELLED')
      .slice(0, 5)
      .map(order => ({
        id: order.id,
        name: order.user.fullName,
        email: order.user.email,
        amount: formatToVND(order.payment[0]?.amount || 0),

      }))
}

export const calculatePercentageChange = (currentValue: number, previousValue: number) => {
  if (previousValue === 0) return 100
  return Number((((currentValue - previousValue) / previousValue) * 100).toFixed(1))
}

export const getMonthlyComparisons = (orders: any[]) => {
  const currentDate = new Date()
  const currentMonth = currentDate.getMonth()
  const currentYear = currentDate.getFullYear()
  const previousMonth = currentMonth === 0 ? 11 : currentMonth - 1
  const previousYear = currentMonth === 0 ? currentYear - 1 : currentYear

  const currentMonthOrders = orders.filter(order => {
    const date = new Date(order.createdAt)
    return date.getMonth() === currentMonth && 
           date.getFullYear() === currentYear && 
           order.status !== 'CANCELLED'
  })

  const previousMonthOrders = orders.filter(order => {
    const date = new Date(order.createdAt)
    return date.getMonth() === previousMonth && 
           date.getFullYear() === previousYear && 
           order.status !== 'CANCELLED'
  })

  return {
    revenue: {
      current: calculateTotalRevenue(currentMonthOrders),
      previous: calculateTotalRevenue(previousMonthOrders)
    },
    customers: {
      current: currentMonthOrders.reduce((acc, order) => {
        acc.add(order.userId)
        return acc
      }, new Set()).size,
      previous: previousMonthOrders.reduce((acc, order) => {
        acc.add(order.userId)
        return acc
      }, new Set()).size
    },
    orders: {
      current: currentMonthOrders.length,
      previous: previousMonthOrders.length
    },
  }
}
