'use client'

import React, { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogTrigger } from "@/components/ui/dialog"
import { formatToVND } from "@/lib/utils"
import { ProductDialog } from "@/components/products/product-dialog"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from "@/components/ui/select"

type Product = {
  id: string
  name: string
  price: number
  quantity: number
  description: string | null
}

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [search, setSearch] = useState("")
  const [editingProduct, setEditingProduct] = useState<Product | null>(null)
  const [dialogContent, setDialogContent] = useState<'add' | 'edit' | null>(null)
  const isDialogOpen = Boolean(dialogContent)
  const [formData, setFormData] = useState({
    name: "",
    price: "",
    quantity: "",
    description: "",
  })
  
  // Pagination state
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  
  const filteredProducts = products.filter(product =>
      product.name.toLowerCase().includes(search.toLowerCase())
  )
  
  // Calculate pagination
  const totalPages = Math.ceil(filteredProducts.length / pageSize)
  const startIndex = (currentPage - 1) * pageSize
  const endIndex = startIndex + pageSize
  const paginatedProducts = filteredProducts.slice(startIndex, endIndex)
  
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
  
  const openAddDialog = () => {
    resetForm()
    setDialogContent('add')
  }

  const fetchProducts = () => {
    fetch('/api/products')
      .then(res => res.json())
      .then(data => {
        // Handle both formats - array or object with products property
        const productArray = Array.isArray(data) ? data : data.products || [];
        setProducts(productArray);
      })
  }
  
  useEffect(() => {
    fetchProducts()
  }, [])
  
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value })
  }

  const handleAddProduct = async () => {
    const response = await fetch('/api/products', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
    })

    if (response.ok) {
      fetchProducts()
      setDialogContent(null)
      resetForm()
    }
  }

  const handleEditProduct = async () => {
    if (!editingProduct) return

    const response = await fetch(`/api/products?id=${editingProduct.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
    })

    if (response.ok) {
      fetchProducts()
      setDialogContent(null)
      resetForm()
    }
  }

  const handleDeleteProduct = async (id: string) => {
    const response = await fetch(`/api/products?id=${id}`, {
      method: 'DELETE',
    })

    if (response.ok) {
      fetchProducts()
    }
  }

  const openEditDialog = (product: Product) => {
    setEditingProduct(product)
    setFormData({
      name: product.name,
      price: product.price.toString(),
      quantity: product.quantity.toString(),
      description: product.description || '',
    })
    setDialogContent('edit')
  }
  
  const resetForm = () => {
    setFormData({
      name: "",
      price: "",
      quantity: "",
      description: "",
    })
    setEditingProduct(null)
  }

  return (
    <div className="w-full space-y-4 p-4 md:p-8 pt-6">
      <div className="flex items-center justify-between w-full">
        <h2 className="text-3xl font-bold tracking-tight">Products</h2>
        <Dialog>
          <DialogTrigger asChild>
            <Button onClick={openAddDialog}>Add Product</Button>
          </DialogTrigger>
          {isDialogOpen && (
              <ProductDialog
                  isEdit={dialogContent === 'edit'}
                  formData={formData}
                  onInputChange={handleInputChange}
                  onSubmit={dialogContent === 'edit' ? handleEditProduct : handleAddProduct}
              />
          )}
        </Dialog>
      </div>
  
      <div className="flex flex-col sm:flex-row gap-2 sm:items-center justify-between">
        <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
          <Input
            placeholder="Search products..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-sm"
          />
        </div>
        
        <div className="flex items-center gap-2">
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
          <CardTitle>Inventory Overview</CardTitle>
          <CardDescription>Showing {startIndex + 1}-{Math.min(endIndex, filteredProducts.length)} of {filteredProducts.length} products.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Price</TableHead>
                <TableHead>Quantity</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {paginatedProducts.map((product) => (
                <TableRow key={product.id}>
                  <TableCell>{product.name}</TableCell>
                  <TableCell>{formatToVND(product.price)}</TableCell>
                  <TableCell>{product.quantity}</TableCell>
                  <TableCell>
                    <Badge variant={
                      product.quantity === 0 ? 'destructive' :
                          product.quantity <= 5 ? 'secondary' :
                              'default'
                    }>
                      {product.quantity === 0 ? 'Out of Stock' :
                          product.quantity <= 5 ? 'Running Low' :
                              'In Stock'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Dialog>
                        <DialogTrigger asChild>
                          <Button variant="outline" size="sm" onClick={() => openEditDialog(product)}>
                            Edit
                          </Button>
                        </DialogTrigger>
                        {isDialogOpen && dialogContent === 'edit' && (
                            <ProductDialog
                                isEdit={true}
                                formData={formData}
                                onInputChange={handleInputChange}
                                onSubmit={handleEditProduct}
                            />
                        )}
                      </Dialog>
                      <Button variant="destructive" size="sm" onClick={() => handleDeleteProduct(product.id)}>
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          
          {/* Pagination */}
          {filteredProducts.length > 0 && (
            <div className="mt-6 flex flex-col sm:flex-row items-center justify-between gap-4 px-4">
              <div className="text-sm text-muted-foreground">
                Showing {startIndex + 1}-{Math.min(endIndex, filteredProducts.length)} of {filteredProducts.length} products
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
  )
}
