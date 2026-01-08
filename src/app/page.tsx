"use client"

import ProductGrid from "@/components/products/ProductGrid";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import {useEffect, useState} from "react";
import { Product } from '@prisma/client'

export default function Home() {
  const [products, setProducts] = useState<Product[]>([])

  useEffect(() => {
    async function fetchProducts() {
      const response = await fetch('/api/products?sort=newest&take=8')
      const data = await response.json()
      setProducts(data.products)
    }

    fetchProducts()
  }, [])
  
  return (
    <div className="space-y-16">
      {/* Hero Section */}
      <section className="relative">
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-xl overflow-hidden">
          <div className="container mx-auto py-16 px-4 sm:px-6 lg:px-8 relative z-10">
            <div className="max-w-xl">
              <h1 className="text-4xl md:text-5xl font-bold text-white mb-4">
                Meo Stationery
              </h1>
              <p className="text-blue-100 text-lg mb-8">
                Khám phá bộ sưu tập văn phòng phẩm chất lượng cao với thiết kế độc đáo, 
                giúp không gian làm việc của bạn trở nên sáng tạo và hiệu quả hơn.
              </p>
              <Link href="/products">
                <Button size="lg" className="bg-white text-blue-600 hover:bg-blue-50">
                  Khám phá ngay
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </div>
          </div>
        </div>
        <div className="absolute inset-0 bg-[url('/stationery-pattern.png')] opacity-10 mix-blend-overlay"></div>
      </section>

      {/* New Arrivals */}
      <section className="container mx-auto px-4">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold">Sản phẩm mới</h2>
          <Link href="/products">
            <Button variant="ghost" className="text-blue-600 hover:text-blue-800">
              Xem tất cả
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </Link>
        </div>
        <ProductGrid products={products}/>
      </section>
    </div>
  )
}
