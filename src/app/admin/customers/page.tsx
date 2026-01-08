"use client"

import { useEffect, useState } from "react"
import { formatToVND } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import {
    Pagination,
    PaginationContent,
    PaginationEllipsis,
    PaginationItem,
    PaginationLink,
    PaginationNext,
    PaginationPrevious,
} from "@/components/ui/pagination"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

type Customer = {
    id: number
    name: string
    email: string
    totalOrders: number
    totalSpent: number
    lastOrderDate: string
    orders: {
        id: string
        date: string
        total: number
        status: string
    }[]
}
export default function CustomersPage() {
    const [customers, setCustomers] = useState([])
    const [search, setSearch] = useState("")
    const [loading, setLoading] = useState(true)
    const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null)
    
    // Pagination state
    const [currentPage, setCurrentPage] = useState(1)
    const [pageSize, setPageSize] = useState(10)

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
    
    useEffect(() => {
        async function fetchCustomers() {
            try {
                const response = await fetch('/api/customers')
                const data = await response.json()
                setCustomers(data)
            } catch (error) {
                console.error('Failed to fetch customers:', error)
            } finally {
                setLoading(false)
            }
        }

        fetchCustomers()
    }, [])

    const filteredCustomers = customers.filter(
        (customer : Customer) =>
            customer.name.toLowerCase().includes(search.toLowerCase()) ||
            customer.email.toLowerCase().includes(search.toLowerCase())
    )
    
    // Calculate pagination
    const totalPages = Math.ceil(filteredCustomers.length / pageSize)
    const startIndex = (currentPage - 1) * pageSize
    const endIndex = startIndex + pageSize
    const paginatedCustomers = filteredCustomers.slice(startIndex, endIndex)
    
    // Handle page change
    const handlePageChange = (page: number) => {
        setCurrentPage(page)
    }
    
    // Handle page size change
    const handlePageSizeChange = (value: string) => {
        setPageSize(Number(value))
        setCurrentPage(1) // Reset to first page when changing page size
    }
    
    // Generate page numbers for pagination
    const getPageNumbers = () => {
        const pages: (number | string)[] = []
        const maxPagesToShow = 5
        
        if (totalPages <= maxPagesToShow) {
            // Show all pages if total pages are less than or equal to maxPagesToShow
            for (let i = 1; i <= totalPages; i++) {
                pages.push(i)
            }
        } else {
            // Always show first page
            pages.push(1)
            
            // Calculate start and end of middle section
            let startPage = Math.max(2, currentPage - 1)
            let endPage = Math.min(totalPages - 1, currentPage + 1)
            
            // Adjust if we're near the beginning
            if (currentPage <= 3) {
                endPage = Math.min(totalPages - 1, 4)
            }
            
            // Adjust if we're near the end
            if (currentPage >= totalPages - 2) {
                startPage = Math.max(2, totalPages - 3)
            }
            
            // Add ellipsis after first page if needed
            if (startPage > 2) {
                pages.push('ellipsis1')
            }
            
            // Add middle pages
            for (let i = startPage; i <= endPage; i++) {
                pages.push(i)
            }
            
            // Add ellipsis before last page if needed
            if (endPage < totalPages - 1) {
                pages.push('ellipsis2')
            }
            
            // Always show last page
            if (totalPages > 1) {
                pages.push(totalPages)
            }
        }
        
        return pages
    }

    return (
        <div className="flex-1 space-y-4 p-4 md:p-8 pt-6">
            <div className="space-y-4">
                <h2 className="text-3xl font-bold tracking-tight">Customers</h2>
    
                <div className="flex items-center justify-between">
                    <Input
                        placeholder="Search customers..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="max-w-sm"
                    />
                    <div className="flex items-center space-x-2">
                        <span className="text-sm text-muted-foreground">Items per page:</span>
                        <Select
                            value={pageSize.toString()}
                            onValueChange={handlePageSizeChange}
                        >
                            <SelectTrigger className="h-8 w-[70px]">
                                <SelectValue placeholder={pageSize} />
                            </SelectTrigger>
                            <SelectContent side="top">
                                {[10, 20, 30, 50, 100].map((size) => (
                                    <SelectItem key={size} value={size.toString()}>
                                        {size}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
    
                <Card>
                    <CardHeader>
                        <CardTitle>Customer List</CardTitle>
                        <CardDescription>View and manage all customer information. Showing {startIndex + 1}-{Math.min(endIndex, filteredCustomers.length)} of {filteredCustomers.length} customers</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Name</TableHead>
                                    <TableHead>Email</TableHead>
                                    <TableHead>Total Orders</TableHead>
                                    <TableHead>Total Spent</TableHead>
                                    <TableHead>Last Order</TableHead>
                                    <TableHead>Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {loading ? (
                                    <TableRow>
                                        <TableCell colSpan={6} className="h-24 text-center">
                                            Loading customers...
                                        </TableCell>
                                    </TableRow>
                                ) : paginatedCustomers.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={6} className="h-24 text-center">
                                            No customers found.
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    paginatedCustomers.map((customer : Customer) => (
                                        <TableRow key={customer.id}>
                                            <TableCell className="font-medium">{customer.name}</TableCell>
                                            <TableCell>{customer.email}</TableCell>
                                            <TableCell>{customer.totalOrders}</TableCell>
                                            <TableCell>{formatToVND(customer.totalSpent)}</TableCell>
                                            <TableCell>{new Date(customer.lastOrderDate).toLocaleDateString()}</TableCell>
                                            <TableCell>
                                                <Dialog>
                                                    <DialogTrigger asChild>
                                                        <Button variant="outline" size="sm" onClick={() => setSelectedCustomer(customer)}>
                                                            View Orders
                                                        </Button>
                                                    </DialogTrigger>
                                                    <DialogContent className="sm:max-w-[625px]">
                                                        <DialogHeader>
                                                            <DialogTitle>{customer.name}'s Orders</DialogTitle>
                                                            <DialogDescription>Order history for {customer.email}</DialogDescription>
                                                        </DialogHeader>
                                                        <Table>
                                                            <TableHeader>
                                                                <TableRow>
                                                                    <TableHead>Order ID</TableHead>
                                                                    <TableHead>Date</TableHead>
                                                                    <TableHead>Total</TableHead>
                                                                    <TableHead>Status</TableHead>
                                                                </TableRow>
                                                            </TableHeader>
                                                            <TableBody>
                                                                {customer.orders
                                                                    .filter(order => order.status !== 'CANCELLED')
                                                                    .map((order) => (
                                                                    <TableRow key={order.id}>
                                                                        <TableCell>{order.id}</TableCell>
                                                                        <TableCell>{order.date}</TableCell>
                                                                        <TableCell>{formatToVND(order.total)}</TableCell>
                                                                        <TableCell>
                                                                            <Badge className={`${getStatusColor(order.status)} text-white`}>
                                                                                {order.status}
                                                                            </Badge>
                                                                        </TableCell>
                                                                    </TableRow>
                                                                ))}
                                                            </TableBody>
                                                        </Table>
                                                    </DialogContent>
                                                </Dialog>
                                            </TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                        
                        {/* Pagination */}
                        {filteredCustomers.length > 0 && (
                            <div className="mt-6 flex flex-col sm:flex-row items-center justify-between gap-4">
                                <div className="flex items-center gap-2">
                                    <span className="text-sm text-muted-foreground">
                                        Showing {startIndex + 1}-{Math.min(endIndex, filteredCustomers.length)} of {filteredCustomers.length}
                                    </span>
                                </div>
                                
                                <Pagination className="ml-auto">
                                    <PaginationContent>
                                        <PaginationItem>
                                            <PaginationPrevious 
                                                onClick={() => currentPage > 1 && handlePageChange(currentPage - 1)}
                                                className={currentPage === 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
                                            />
                                        </PaginationItem>
                                        
                                        {getPageNumbers().map((page, index) => (
                                            <PaginationItem key={`page-${index}`}>
                                                {page === 'ellipsis1' || page === 'ellipsis2' ? (
                                                    <PaginationEllipsis />
                                                ) : (
                                                    <PaginationLink 
                                                        isActive={page === currentPage}
                                                        onClick={() => typeof page === 'number' && handlePageChange(page)}
                                                        className="cursor-pointer"
                                                    >
                                                        {page}
                                                    </PaginationLink>
                                                )}
                                            </PaginationItem>
                                        ))}
                                        
                                        <PaginationItem>
                                            <PaginationNext 
                                                onClick={() => currentPage < totalPages && handlePageChange(currentPage + 1)}
                                                className={currentPage === totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
                                            />
                                        </PaginationItem>
                                    </PaginationContent>
                                </Pagination>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}
