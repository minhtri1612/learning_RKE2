'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import Image from "next/image"
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatToVND } from "@/lib/utils"
import { Minus, Plus, ShoppingCart, Trash2, ArrowLeft, ShoppingBag } from "lucide-react"
import { toast } from "sonner"
import { Card, CardContent } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'

type CartItem = {
  id: number
  name: string
  price: number
  quantity: number
  stock: number
}

export default function CartPage() {
  const [cartItems, setCartItems] = useState<CartItem[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const storedCart = localStorage.getItem('cart')
    if (storedCart) {
      setCartItems(JSON.parse(storedCart))
    }
    setIsLoading(false)
  }, [])

  const validateQuantities = async () => {
    for (const item of cartItems) {
      const response = await fetch(`/api/products?id=${item.id}`)
      const product = await response.json()
      if (item.quantity > product.quantity) {
        toast.error("Số lượng không hợp lệ", {
          description: `Sản phẩm "${item.name}" vượt quá số lượng trong kho. Vui lòng kiểm tra lại số lượng của sản phẩm!.`,
        })
        return false
      }
    }
    return true
  }
  
  const updateQuantity = (id: number, newQuantity: number) => {
    const updatedCart = cartItems.map(item => 
      item.id === id ? { ...item, quantity: newQuantity } : item
    )
    setCartItems(updatedCart)
    localStorage.setItem('cart', JSON.stringify(updatedCart))
    window.dispatchEvent(new Event('cartUpdated'))
  }

  const removeItem = (id: number) => {
    const updatedCart = cartItems.filter(item => item.id !== id)
    setCartItems(updatedCart)
    localStorage.setItem('cart', JSON.stringify(updatedCart))
    window.dispatchEvent(new Event('cartUpdated'))
    
    toast.success("Đã xóa sản phẩm", {
      description: "Sản phẩm đã được xóa khỏi giỏ hàng của bạn.",
    })
  }

  const total = cartItems.reduce((sum, item) => sum + item.price * item.quantity, 0)

  if (isLoading) {
    return (
      <div className="container mx-auto py-10 px-4">
        <h1 className="text-3xl font-bold mb-5">Giỏ Hàng Của Bạn</h1>
        <div className="animate-pulse space-y-4">
          <div className="h-12 bg-gray-200 rounded"></div>
          <div className="h-64 bg-gray-200 rounded"></div>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto py-10 px-4">
      <div className="flex items-center mb-6">
        <ShoppingCart className="h-6 w-6 mr-2 text-blue-600" />
        <h1 className="text-3xl font-bold">Giỏ Hàng Của Bạn</h1>
      </div>
      
      {cartItems.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2">
            <Card>
              <CardContent className="p-6">
                <div className="hidden md:block">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[100px]">Hình ảnh</TableHead>
                        <TableHead>Sản phẩm</TableHead>
                        <TableHead>Giá</TableHead>
                        <TableHead>Số lượng</TableHead>
                        <TableHead>Tổng</TableHead>
                        <TableHead className="text-right">Thao tác</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {cartItems.map((item) => (
                        <TableRow key={item.id}>
                          <TableCell>
                            <div className="w-20 h-20 relative rounded overflow-hidden">
                              <img
                                src={`/products/${item.id}/0.jpg`}
                                alt={item.name}
                                className="object-cover w-full h-full"
                                onError={(e) => {
                                  e.currentTarget.src = "/placeholder.svg"
                                }}
                              />
                            </div>
                          </TableCell>
                          <TableCell>
                            <Link href={`/product/${item.id}`} className="font-medium hover:text-blue-600 transition-colors">
                              {item.name}
                            </Link>
                          </TableCell>
                          <TableCell>{formatToVND(item.price)}</TableCell>
                          <TableCell>
                            <div className="inline-flex items-center border rounded-md">
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => updateQuantity(item.id, Math.max(1, item.quantity - 1))}
                                disabled={item.quantity <= 1}
                                className="h-8 w-8"
                              >
                                <Minus className="h-3 w-3" />
                              </Button>
                              <input
                                type="text"
                                value={item.quantity}
                                onChange={(e) => {
                                  const value = Number.parseInt(e.target.value)
                                  if (!isNaN(value) && value >= 1 && value <= item.stock) {
                                    updateQuantity(item.id, value)
                                  }
                                }}
                                className="w-10 h-8 text-center focus:outline-none text-sm"
                                inputMode="numeric"
                                pattern="[0-9]*"
                              />
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => updateQuantity(item.id, Math.min(item.stock, item.quantity + 1))}
                                disabled={item.quantity >= item.stock}
                                className="h-8 w-8"
                              >
                                <Plus className="h-3 w-3" />
                              </Button>
                            </div>
                          </TableCell>
                          <TableCell className="font-medium">{formatToVND(item.price * item.quantity)}</TableCell>
                          <TableCell className="text-right">
                            <Button variant="ghost" size="icon" className="text-red-500 hover:text-red-700 hover:bg-red-50" onClick={() => removeItem(item.id)}>
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                
                {/* Mobile view */}
                <div className="md:hidden space-y-6">
                  {cartItems.map((item) => (
                    <div key={item.id} className="border-b pb-6 last:border-b-0">
                      <div className="flex gap-4">
                        <div className="w-20 h-20 relative rounded overflow-hidden flex-shrink-0">
                          <img
                            src={`/products/${item.id}/0.jpg`}
                            alt={item.name}
                            className="object-cover w-full h-full"
                            onError={(e) => {
                              e.currentTarget.src = "/placeholder.svg"
                            }}
                          />
                        </div>
                        <div className="flex-grow">
                          <Link href={`/product/${item.id}`} className="font-medium hover:text-blue-600 transition-colors">
                            {item.name}
                          </Link>
                          <p className="text-gray-600 mt-1">{formatToVND(item.price)}</p>
                          
                          <div className="flex justify-between items-center mt-3">
                            <div className="inline-flex items-center border rounded-md">
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => updateQuantity(item.id, Math.max(1, item.quantity - 1))}
                                disabled={item.quantity <= 1}
                                className="h-8 w-8"
                              >
                                <Minus className="h-3 w-3" />
                              </Button>
                              <input
                                type="text"
                                value={item.quantity}
                                onChange={(e) => {
                                  const value = Number.parseInt(e.target.value)
                                  if (!isNaN(value) && value >= 1 && value <= item.stock) {
                                    updateQuantity(item.id, value)
                                  }
                                }}
                                className="w-8 h-8 text-center focus:outline-none text-sm"
                                inputMode="numeric"
                                pattern="[0-9]*"
                              />
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => updateQuantity(item.id, Math.min(item.stock, item.quantity + 1))}
                                disabled={item.quantity >= item.stock}
                                className="h-8 w-8"
                              >
                                <Plus className="h-3 w-3" />
                              </Button>
                            </div>
                            
                            <Button variant="ghost" size="icon" className="text-red-500 hover:text-red-700 hover:bg-red-50" onClick={() => removeItem(item.id)}>
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                          
                          <p className="text-right font-medium mt-2">
                            {formatToVND(item.price * item.quantity)}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
            
            <div className="mt-6">
              <Link href="/">
                <Button variant="outline" className="gap-2">
                  <ArrowLeft className="h-4 w-4" />
                  Tiếp tục mua sắm
                </Button>
              </Link>
            </div>
          </div>
          
          <div>
            <Card>
              <CardContent className="p-6">
                <h2 className="text-xl font-bold mb-4">Tóm tắt đơn hàng</h2>
                
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Tạm tính ({cartItems.reduce((sum, item) => sum + item.quantity, 0)} sản phẩm)</span>
                    <span>{formatToVND(total)}</span>
                  </div>
                  
                  <div className="flex justify-between">
                    <span className="text-gray-600">Phí vận chuyển</span>
                    <span>Miễn phí</span>
                  </div>
                </div>
                
                <Separator className="my-4" />
                
                <div className="flex justify-between font-bold text-lg mb-6">
                  <span>Tổng cộng</span>
                  <span className="text-blue-600">{formatToVND(total)}</span>
                </div>
                
                <Button
                  className="w-full bg-blue-600 hover:bg-blue-700"
                  size="lg"
                  onClick={async () => {
                    const isValid = await validateQuantities()
                    if (isValid) {
                      window.location.href = '/checkout/shipping'
                    }
                  }}
                >
                  <ShoppingBag className="mr-2 h-4 w-4" />
                  Tiến hành thanh toán
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : (
        <div className="text-center py-10 bg-gray-50 rounded-lg shadow-sm">
          <div className="max-w-md mx-auto">
            <div className="w-20 h-20 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-6">
              <ShoppingCart className="h-10 w-10 text-blue-600" />
            </div>
            <h2 className="text-2xl font-bold mb-2">Giỏ hàng của bạn đang trống</h2>
            <p className="text-gray-600 mb-8">Hãy thêm một vài sản phẩm vào giỏ hàng của bạn và quay lại đây.</p>
            <div className="flex justify-center mb-8">
              <Image
                src="/shopping.jpg"
                alt="Empty Cart"
                width={300}
                height={300}
                className="object-contain rounded-lg"
                style={{
                  backgroundColor: "transparent",
                  border: "none",
                  outline: "none",
                  boxShadow: "none",
                }}
              />
            </div>
            <Link href="/">
              <Button size="lg" className="bg-blue-600 hover:bg-blue-700">
                <ShoppingBag className="mr-2 h-4 w-4" />
                Tiếp tục mua sắm
              </Button>
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}
