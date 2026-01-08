"use client"

import { useState } from "react"
import { 
    Dialog, 
    DialogContent, 
    DialogTitle, 
    DialogHeader,
    DialogFooter
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { 
    Select, 
    SelectContent, 
    SelectItem, 
    SelectTrigger, 
    SelectValue 
} from "@/components/ui/select"
import { formatToVND } from "@/lib/utils"
import { toast } from "@/components/ui/use-toast"

interface OrderItem {
    orderId: number
    productId: number
    quantity: number
    product: {
        name: string
        price: number
    }
}

interface Address {
    id: number
    street: string
    ward: string | null
    district: string | null
    city: string | null
    country: string | null
    apartment: string | null
}

interface Order {
    id: number
    userId: number
    status: 'PENDING' | 'PROCESSING' | 'SHIPPED' | 'DELIVERED' | 'CANCELLED'
    createdAt: string
    user: {
        fullName: string
        email: string
        address: Address
    }
    payment: {
        amount: number
    }[]
    items: OrderItem[]
}

interface OrderDetailsDialogProps {
    order: Order | null
    open: boolean
    onOpenChange: (open: boolean) => void
    onStatusUpdate: (orderId: number, newStatus: string) => Promise<void>
    updatingStatus: boolean
}

export function OrderDetailsDialog({ 
    order, 
    open, 
    onOpenChange, 
    onStatusUpdate, 
    updatingStatus 
}: OrderDetailsDialogProps) {
    const getStatusColor = (status: string) => {
        switch (status) {
            case "DELIVERED":
                return "bg-green-500"
            case "PROCESSING":
                return "bg-blue-500"
            case "SHIPPED":
                return "bg-yellow-500"
            case "PENDING":
                return "bg-orange-500"
            case "CANCELLED":
                return "bg-red-500"
            default:
                return "bg-gray-500"
        }
    }

    if (!order) return null

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[550px]">
                <DialogHeader>
                    <DialogTitle>Order Details</DialogTitle>
                </DialogHeader>
                <div className="space-y-6">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <h3 className="text-sm font-medium mb-2">Order Information</h3>
                            <div className="grid grid-cols-2 gap-2 bg-muted/50 p-3 rounded-md">
                                <div className="text-sm font-medium">Order ID:</div>
                                <div className="text-sm">{order.id}</div>

                                <div className="text-sm font-medium">Status:</div>
                                <div className="text-sm">
                                    <Badge className={`${getStatusColor(order.status)} text-white`}>
                                        {order.status}
                                    </Badge>
                                </div>

                                <div className="text-sm font-medium">Date:</div>
                                <div className="text-sm">
                                    {new Date(order.createdAt).toLocaleDateString()}
                                </div>
                            </div>
                        </div>
                        
                        <div>
                            <h3 className="text-sm font-medium mb-2">Customer Information</h3>
                            <div className="bg-muted/50 p-3 rounded-md">
                                <div className="text-sm"><span className="font-medium">Name:</span> {order.user.fullName}</div>
                                <div className="text-sm"><span className="font-medium">Email:</span> {order.user.email}</div>
                            </div>
                        </div>
                    </div>
                        
                    <div>
                        <h3 className="text-sm font-medium mb-2">Shipping Address</h3>
                        <div className="bg-muted/50 p-3 rounded-md">
                            {order.user.address ? (
                                <>
                                    {order.user.address.street && (
                                        <div className="text-sm mb-1"><span className="font-medium">Street:</span> {order.user.address.street}</div>
                                    )}
                                    {order.user.address.apartment && (
                                        <div className="text-sm mb-1"><span className="font-medium">Apartment:</span> {order.user.address.apartment}</div>
                                    )}
                                    {order.user.address.ward && (
                                        <div className="text-sm mb-1"><span className="font-medium">Ward:</span> {order.user.address.ward}</div>
                                    )}
                                    {order.user.address.district && (
                                        <div className="text-sm mb-1"><span className="font-medium">District:</span> {order.user.address.district}</div>
                                    )}
                                    {order.user.address.city && (
                                        <div className="text-sm mb-1"><span className="font-medium">City:</span> {order.user.address.city}</div>
                                    )}
                                    {order.user.address.country && (
                                        <div className="text-sm"><span className="font-medium">Country:</span> {order.user.address.country}</div>
                                    )}
                                </>
                            ) : (
                                <div className="text-sm text-muted-foreground">No address information available</div>
                            )}
                        </div>
                    </div>

                    <div>
                        <h3 className="text-sm font-medium mb-2">Order Items</h3>
                        <div className="bg-muted/50 p-3 rounded-md max-h-[200px] overflow-y-auto">
                            <div className="space-y-3">
                                {order.items?.map((item) => (
                                    <div key={`${item.orderId}-${item.productId}`}
                                            className="flex justify-between items-center border-b pb-2 last:border-0">
                                        <div>
                                            <div className="text-sm font-medium">{item.product.name}</div>
                                            <div className="text-sm text-muted-foreground">
                                                Quantity: {item.quantity}
                                            </div>
                                        </div>
                                        <div className="text-sm font-medium">
                                            {formatToVND(item.product.price * item.quantity)}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    <div className="flex justify-between items-center pt-4 border-t">
                        <div className="text-sm font-medium">Total Amount:</div>
                        <div className="text-lg font-bold">
                            {formatToVND(order.payment[0]?.amount || 0)}
                        </div>
                    </div>
                    
                    <DialogFooter>
                        <div className="w-full flex justify-between items-center gap-2">
                            <Select
                                value={order.status}
                                onValueChange={(value) => onStatusUpdate(order.id, value)}
                                disabled={updatingStatus}
                            >
                                <SelectTrigger className="w-[180px]">
                                    <SelectValue placeholder="Update Status" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="PENDING">Pending</SelectItem>
                                    <SelectItem value="PROCESSING">Processing</SelectItem>
                                    <SelectItem value="SHIPPED">Shipped</SelectItem>
                                    <SelectItem value="DELIVERED">Delivered</SelectItem>
                                    <SelectItem value="CANCELLED">Cancelled</SelectItem>
                                </SelectContent>
                            </Select>
                            
                            <Button 
                                variant="outline" 
                                onClick={() => onOpenChange(false)}
                            >
                                Close
                            </Button>
                        </div>
                    </DialogFooter>
                </div>
            </DialogContent>
        </Dialog>
    )
}
