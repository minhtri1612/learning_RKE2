'use client'

import Link from 'next/link'
import Image from 'next/image'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useCart } from "@/hooks/useCart"
import { Skeleton } from "@/components/ui/skeleton"
import { formatToVND } from "@/lib/utils";
import { toast } from "sonner";
import { Product } from "@prisma/client";
import { ShoppingCart, Eye, Badge } from "lucide-react";
import { Badge as UIBadge } from "@/components/ui/badge";

function SkeletonCard() {
  return (
    <div className="flex flex-col space-y-3">
      <Skeleton className="h-[250px] w-full rounded-xl" />
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    </div>
  )
}

export default function ProductGrid({ products }: { products: Product[] }) {
  const { addItem } = useCart()

  const handleAddToCart = (product: Product) => {
    addItem({
      id: product.id,
      name: product.name,
      price: product.price,
      quantity: 1,
      stock: product.quantity
    })

    toast.success("Đã thêm vào giỏ hàng!", {
      description: `1 ${product.name} đã được thêm vào giỏ hàng của bạn.`,
    })
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
      {products.length > 0 ? (
        products.map((product) => (
          <Card key={product.id} className="group overflow-hidden border border-gray-200 hover:border-blue-300 hover:shadow-md transition-all duration-300">
            <div className="relative">
              <Link href={`/products/${product.id}`}>
                <div className="relative h-64 overflow-hidden">
                  <Image
                    src={`/products/${product.id}/0.jpg`}
                    alt={product.name}
                    width={300}
                    height={300}
                    className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                    style={{ objectFit: 'cover' }}
                    placeholder="blur"
                    blurDataURL="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+P+/HgAEtAJJXIDTjgAAAABJRU5ErkJggg=="
                  />
                  <div className="absolute inset-0 bg-black opacity-0 group-hover:opacity-10 transition-opacity duration-300"></div>
                </div>
              </Link>
              <div className="absolute top-2 right-2 flex flex-col gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                <Link href={`/products/${product.id}`}>
                  <Button size="icon" variant="secondary" className="rounded-full h-9 w-9 bg-white hover:bg-blue-50 text-blue-600">
                    <Eye className="h-4 w-4" />
                  </Button>
                </Link>
              </div>
            </div>
            <CardContent className="p-4">
              <Link href={`/products/${product.id}`}>
                <h3 className="text-lg font-medium mb-2 line-clamp-2 group-hover:text-blue-600 transition-colors">{product.name}</h3>
              </Link>
              <p className="text-lg font-semibold text-blue-600">{formatToVND(product.price)}</p>
              <div className="mt-2 flex items-center">
                {product.quantity > 0 ? (
                  <UIBadge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                    Còn hàng
                  </UIBadge>
                ) : (
                  <UIBadge variant="outline" className="bg-red-50 text-red-700 border-red-200">
                    Hết hàng
                  </UIBadge>
                )}
              </div>
            </CardContent>
            <CardFooter className="p-4 pt-0">
              <Button
                onClick={() => handleAddToCart(product)}
                disabled={product.quantity === 0}
                className="w-full"
                variant="default"
              >
                <ShoppingCart className="mr-2 h-4 w-4" />
                Thêm vào giỏ
              </Button>
            </CardFooter>
          </Card>
        ))
      ) : (
        <div className="col-span-full text-center py-10">
          <h3 className="text-lg font-medium text-gray-500">Không tìm thấy sản phẩm nào</h3>
          <p className="text-gray-400 mt-2">Vui lòng thử lại với bộ lọc khác</p>
        </div>
      )}
    </div>
  )
}
