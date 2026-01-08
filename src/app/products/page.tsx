"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import ProductGrid from "@/components/products/ProductGrid";
import ProductsFilter from "@/components/products/ProductsFilter";
import { Product } from "@prisma/client";

interface PriceRange {
  min: number;
  max: number;
}

interface ProductsResponse {
  products: Product[];
  priceRange?: PriceRange;
}

function Products() {
  const searchParams = useSearchParams();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [minPrice, setMinPrice] = useState(0);
  const [maxPrice, setMaxPrice] = useState(100000);
  
  // Get filter values from URL
  const searchQuery = searchParams.get("search") || "";
  const selectedSort = searchParams.get("sort") || "newest";
  const selectedMinPrice = searchParams.get("minPrice") ? parseInt(searchParams.get("minPrice") as string) : minPrice;
  const selectedMaxPrice = searchParams.get("maxPrice") ? parseInt(searchParams.get("maxPrice") as string) : maxPrice;

  // Fetch products based on filters
  useEffect(() => {
    async function fetchProducts() {
      setLoading(true);
      try {
        // Build query parameters
        const params = new URLSearchParams(searchParams.toString());
        
        if (!params.has('take')) {
          params.set('take', '100'); // Or any sufficiently large number
        }
        
        // Fetch products
        const response = await fetch(`/api/products?${params.toString()}`);
        const data: ProductsResponse = await response.json();
        setProducts(data.products || []);

        // Set price range if available
        if (data.priceRange) {
          setMinPrice(data.priceRange.min);
          setMaxPrice(data.priceRange.max);
        }
      } catch (error) {
        console.error("Error fetching products:", error);
      } finally {
        setLoading(false);
      }
    }

    fetchProducts();
  }, [searchParams]);

  return (
    <div className="container mx-auto py-10 px-4">
      <h1 className="text-3xl font-bold mb-8">Tất cả sản phẩm</h1>
      
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        {/* Filters sidebar */}
        <div className="lg:col-span-1">
          <ProductsFilter 
            minPrice={minPrice}
            maxPrice={maxPrice}
            selectedSort={selectedSort}
            selectedMinPrice={selectedMinPrice}
            selectedMaxPrice={selectedMaxPrice}
            searchQuery={searchQuery}
          />
        </div>
        
        {/* Products grid */}
        <div className="lg:col-span-3">
          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="bg-gray-100 rounded-lg h-80 animate-pulse"></div>
              ))}
            </div>
          ) : products.length > 0 ? (
            <ProductGrid products={products} />
          ) : (
            <div className="text-center py-12">
              <h3 className="text-lg font-medium mb-2">Không tìm thấy sản phẩm nào</h3>
              <p className="text-gray-500">Vui lòng thử lại với bộ lọc khác</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ProductsPage() {
  return (
    <Suspense fallback={
      <div className="container mx-auto py-10 px-4">
        <h1 className="text-3xl font-bold mb-8">Tất cả sản phẩm</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="bg-gray-100 rounded-lg h-80 animate-pulse"></div>
          ))}
        </div>
      </div>
    }>
      <Products />
    </Suspense>
  );
}
