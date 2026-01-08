import { prisma } from "@/lib/prisma"
import { NextResponse } from "next/server"

export async function GET(request: Request) {
    try {
        // Get the URL to check for cache-busting parameters
        const url = new URL(request.url);
        
        // Set cache control headers to prevent caching
        const headers = new Headers();
        headers.set('Cache-Control', 'no-store, max-age=0');
        
        const customers = await prisma.user.findMany({
            include: {
                orders: {
                    include: {
                        items: {
                            include: {
                                product: true
                            }
                        },
                        payment: true
                    },
                    orderBy: {
                        createdAt: 'desc'
                    }
                }
            }
        })

        const formattedCustomers = customers.map(customer => {
            const totalOrders = customer.orders.length
            const totalSpent = customer.orders.reduce((acc, order) => {
                const orderTotal = order.payment.reduce((sum, payment) => sum + payment.amount, 0)
                return acc + orderTotal
            }, 0)
            const lastOrder = customer.orders[0]

            return {
                id: customer.id,
                name: customer.fullName,
                email: customer.email,
                totalOrders,
                totalSpent,
                lastOrderDate: lastOrder?.createdAt || 'No orders',
                orders: customer.orders.map(order => ({
                    id: order.id.toString(),
                    date: order.createdAt,
                    total: order.payment.reduce((sum, payment) => sum + payment.amount, 0),
                    status: order.status
                }))
            }
        })

        return NextResponse.json(formattedCustomers, { headers })
    } catch (error) {
        console.error('Failed to fetch customers:', error);
        return NextResponse.json(
            { error: "Failed to fetch customers" }, 
            { status: 500 }
        )
    }
}
