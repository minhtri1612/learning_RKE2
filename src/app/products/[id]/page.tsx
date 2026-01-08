'use client'

import { notFound } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb"
import { formatToVND, getStockStatus } from "@/lib/utils";
import { use, useState, useEffect, useRef } from "react";
import { useCart } from "@/hooks/useCart";
import { toast } from "sonner"
import { ChevronLeft, ChevronRight, Minus, Plus, ShoppingCart, Truck, Package, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

const ProductPage = (props: { params: Promise<{ id: string }> }) => {
  const { addItem } = useCart()
  const [quantity, setQuantity] = useState(1)
  const [product, setProduct] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [productImages, setProductImages] = useState<string[]>([])
  const [selectedImage, setSelectedImage] = useState(0)
  const params = use(props.params)
  const thumbnailsRef = useRef<HTMLDivElement>(null)
  
  const handleAddToCart = () => {
    addItem({
      id: product.id,
      name: product.name,
      price: product.price,
      quantity: quantity,
      stock: product.quantity
    })

    toast.success("Đã thêm vào giỏ hàng!", {
      description: `${quantity} ${product.name} đã được thêm vào giỏ hàng của bạn.`,
    })
  }
  
  const nextImage = () => {
    setSelectedImage((prev) => (prev + 1) % productImages.length)
  }

  const prevImage = () => {
    setSelectedImage((prev) => (prev - 1 + productImages.length) % productImages.length)
  }
  
  useEffect(() => {
    const fetchProduct = async () => {
      try {
        const response = await fetch(`/api/products?id=${params.id}`)
        const data = await response.json()
        if (!data) notFound()
        setProduct(data)
      } catch (error) {
        console.error(error)
        notFound()
      } finally {
        setLoading(false)
      }
    }
    fetchProduct()
  }, [params.id])

  useEffect(() => {
    const loadProductImages = async () => {
      const images: string[] = []
      for(let i = 0; i < 10; i++) {
        const imagePath = `/products/${params.id}/${i}.jpg`
        try {
          const response = await fetch(imagePath, { method: 'HEAD' })
          if (response.ok) {
            images.push(imagePath)
          }
        } catch (error) {
          break
        }
      }
      
      // If no images found, add a placeholder
      if (images.length === 0) {
        images.push("/placeholder.svg")
      }
      
      setProductImages(images)
    }

    loadProductImages()
  }, [params.id])

  useEffect(() => {
    if (thumbnailsRef.current) {
      const selectedThumb = thumbnailsRef.current.children[selectedImage] as HTMLElement
      if (selectedThumb) {
        selectedThumb.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
          inline: 'center'
        })
      }
    }
  }, [selectedImage])
  
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
      </div>
    )
  }
  
  if (!product) return notFound()

  const stockStatus = getStockStatus(product.quantity)
  const stockColor = {
    'IN_STOCK': 'bg-green-500',
    'RUNNING_LOW': 'bg-yellow-500',
    'OUT_OF_STOCK': 'bg-red-500'
  }[stockStatus]
  
  const stockLabel = {
    'IN_STOCK': 'Còn hàng',
    'RUNNING_LOW': 'Sắp hết hàng',
    'OUT_OF_STOCK': 'Hết hàng'
  }[stockStatus]
  
  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6">
        <Link href="/" className="inline-flex items-center text-sm font-medium text-gray-600 hover:text-primary transition-colors">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Quay lại trang chủ
        </Link>
      </div>
      
      <Breadcrumb className="mb-8">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href="/">Trang chủ</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink href="/products">Sản phẩm</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{product.name}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-12 mb-12">
        {/* Product Images */}
        <div className="space-y-4">
          <div className="relative overflow-hidden rounded-xl bg-gray-100 border shadow-sm aspect-square">
            <img
              src={productImages[selectedImage]}
              alt={product.name}
              className="w-full h-full object-contain p-4"
            />
            {productImages.length > 1 && (
              <>
                <button
                  onClick={prevImage}
                  className="absolute left-2 top-1/2 transform -translate-y-1/2 bg-white/80 hover:bg-white shadow-md rounded-full p-2 transition-all"
                  aria-label="Previous image"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <button
                  onClick={nextImage}
                  className="absolute right-2 top-1/2 transform -translate-y-1/2 bg-white/80 hover:bg-white shadow-md rounded-full p-2 transition-all"
                  aria-label="Next image"
                >
                  <ChevronRight className="h-5 w-5" />
                </button>
              </>
            )}
          </div>
          
          {productImages.length > 1 && (
            <div className="relative">
              <div className="overflow-x-auto scrollbar-hide pb-2">
                <div ref={thumbnailsRef} className="flex space-x-2">
                  {productImages.map((image, index) => (
                    <button
                      key={index}
                      onClick={() => setSelectedImage(index)}
                      className={`flex-shrink-0 border rounded-lg overflow-hidden transition-all ${
                        selectedImage === index 
                          ? "ring-2 ring-primary border-transparent" 
                          : "border-gray-200 hover:border-gray-300"
                      }`}
                    >
                      <img
                        src={image}
                        alt={`${product.name} thumbnail ${index + 1}`}
                        width={80}
                        height={80}
                        className="w-20 h-20 object-cover"
                      />
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
        
        {/* Product Info */}
        <div className="flex flex-col">
          <div className="mb-auto">
            <h1 className="text-3xl font-bold mb-2">{product.name}</h1>

            <div className="mb-6">
              <p className="text-3xl font-bold text-primary mb-1">
                {formatToVND(product.price)}
              </p>
              <Badge className={`${stockColor} text-white`}>
                {stockLabel}
              </Badge>
            </div>
            
            {product.description && (
              <div className="mb-8">
                <h2 className="text-lg font-semibold mb-2">Mô tả sản phẩm</h2>
                <p className="text-gray-700">{product.description}</p>
              </div>
            )}
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
              <Card>
                <CardContent className="p-4 flex items-center gap-3">
                  <Truck className="h-5 w-5 text-primary" />
                  <div>
                    <p className="font-medium">Giao hàng nhanh</p>
                    <p className="text-sm text-gray-500">Nhận hàng trong 24h</p>
                  </div>
                </CardContent>
              </Card>
              
              <Card>
                <CardContent className="p-4 flex items-center gap-3">
                  <Package className="h-5 w-5 text-primary" />
                  <div>
                    <p className="font-medium">Đổi trả dễ dàng</p>
                    <p className="text-sm text-gray-500">Trong vòng 7 ngày</p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
          
          <div className="border-t pt-6 mt-4">
            <div className="flex flex-col space-y-4">
              <div className="flex items-center justify-between">
                <span className="font-medium">Số lượng có sẵn:</span>
                <span className="font-semibold">{product.quantity}</span>
              </div>
              
              <div className="flex items-center justify-between">
                <label htmlFor="quantity" className="font-medium">Số lượng đặt:</label>
                <div className="inline-flex items-center border rounded-md shadow-sm">
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => setQuantity(Math.max(1, quantity - 1))}
                    disabled={quantity <= 1}
                    className="h-9 w-9 rounded-r-none"
                  >
                    <Minus className="h-4 w-4" />
                  </Button>
                  <input
                    type="text"
                    value={quantity}
                    onChange={(e) => {
                      const value = Number.parseInt(e.target.value)
                      if (!isNaN(value) && value >= 1 && value <= product.quantity) {
                        setQuantity(value)
                      }
                    }}
                    className="w-14 h-9 text-center focus:outline-none border-y [-moz-appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                    inputMode="numeric"
                    pattern="[0-9]*"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => setQuantity(Math.min(product.quantity, quantity + 1))}
                    disabled={quantity >= product.quantity}
                    className="h-9 w-9 rounded-l-none"
                  >
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              
              <Button
                size="lg"
                disabled={product.quantity === 0}
                onClick={handleAddToCart}
                className="w-full mt-4"
              >
                <ShoppingCart className="mr-2 h-5 w-5" />
                {product.quantity === 0 ? 'Hết hàng' : 'Thêm vào giỏ hàng'}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ProductPage