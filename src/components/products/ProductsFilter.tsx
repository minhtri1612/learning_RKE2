'use client'

import { useState, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Slider } from '@/components/ui/slider'
import { formatToVND } from '@/lib/utils'
import { Search, FilterX, SlidersHorizontal } from 'lucide-react'
import { Separator } from '@/components/ui/separator'
import { Card, CardContent } from '@/components/ui/card'

interface ProductsFilterProps {
  minPrice: number;
  maxPrice: number;
  selectedSort: string;
  selectedMinPrice: number;
  selectedMaxPrice: number;
  searchQuery: string;
}

export default function ProductsFilter({
  minPrice,
  maxPrice,
  selectedSort,
  selectedMinPrice,
  selectedMaxPrice,
  searchQuery
}: ProductsFilterProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const searchInputRef = useRef<HTMLInputElement>(null)
  
  const [priceRange, setPriceRange] = useState<[number, number]>([
    selectedMinPrice || minPrice,
    selectedMaxPrice || maxPrice
  ])
  const [search, setSearch] = useState(searchQuery || '')
  
  // Update URL with filters
  const updateFilters = (params: Record<string, string | null>) => {
    const newParams = new URLSearchParams(searchParams.toString())
    
    // Update or remove params
    Object.entries(params).forEach(([key, value]) => {
      if (value === null) {
        newParams.delete(key)
      } else {
        newParams.set(key, value)
      }
    })
    
    router.push(`/products?${newParams.toString()}`)
  }
  
  // Handle sort change
  const handleSortChange = (value: string) => {
    updateFilters({ sort: value })
  }
  
  // Handle price change
  const handlePriceChange = (value: number[]) => {
    setPriceRange(value as [number, number])
  }
  
  // Apply price filter when button is clicked
  const applyPriceFilter = () => {
    updateFilters({
      minPrice: priceRange[0] === minPrice ? null : priceRange[0].toString(),
      maxPrice: priceRange[1] === maxPrice ? null : priceRange[1].toString()
    })
  }
  
  // Handle search form submission
  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    // Encode the search term properly
    const encodedSearch = search ? encodeURIComponent(search.trim()) : null
    updateFilters({ search: encodedSearch })
  }
  
  // Reset all filters
  const resetFilters = () => {
    // Keep the current URL path but remove all query parameters
    const currentPath = window.location.pathname
    router.push(currentPath)
    setPriceRange([minPrice, maxPrice])
    setSearch('')
    
    // Focus on the search input after reset
    if (searchInputRef.current) {
      searchInputRef.current.focus()
    }
  }
  
  // Check if any filters are applied
  const hasFilters = selectedMinPrice > minPrice || 
    selectedMaxPrice < maxPrice || 
    searchQuery || 
    selectedSort !== 'newest'
  
  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="p-4">
          <form onSubmit={handleSearch} className="flex gap-2 mb-6">
            <div className="relative flex-grow">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-gray-500" />
              <Input
                ref={searchInputRef}
                type="text"
                placeholder="Tìm kiếm sản phẩm..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8"
              />
            </div>
            <Button type="submit">Tìm</Button>
          </form>
          
          {hasFilters && (
            <Button 
              variant="outline" 
              onClick={resetFilters}
              className="w-full mb-4 text-red-500 border-red-200 hover:bg-red-50"
            >
              <FilterX className="mr-2 h-4 w-4" />
              Xóa bộ lọc
            </Button>
          )}
          
          <div className="space-y-6">
            {/* Sort options */}
            <div>
              <h3 className="font-medium mb-3">Sắp xếp theo</h3>
              <RadioGroup 
                defaultValue={selectedSort} 
                onValueChange={handleSortChange}
              >
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="newest" id="newest" />
                  <Label htmlFor="newest">Mới nhất</Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="price-asc" id="price-asc" />
                  <Label htmlFor="price-asc">Giá: Thấp đến cao</Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="price-desc" id="price-desc" />
                  <Label htmlFor="price-desc">Giá: Cao đến thấp</Label>
                </div>
              </RadioGroup>
            </div>
            
            <Separator />
            
            {/* Price range */}
            <div>
              <h3 className="font-medium mb-3">Khoảng giá</h3>
              <div className="px-2 space-y-4">
                <div className="pt-6 pb-2">
                  <Slider
                    defaultValue={priceRange}
                    min={minPrice}
                    max={maxPrice}
                    step={1000}
                    value={priceRange}
                    onValueChange={handlePriceChange}
                    className="mb-6"
                  />
                </div>
                
                <div className="flex justify-between text-sm">
                  <span>{formatToVND(priceRange[0])}</span>
                  <span>{formatToVND(priceRange[1])}</span>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="min-price">Giá thấp nhất</Label>
                    <Input
                      id="min-price"
                      type="number"
                      value={priceRange[0]}
                      onChange={(e) => {
                        const value = parseInt(e.target.value);
                        if (!isNaN(value) && value >= minPrice && value <= priceRange[1]) {
                          setPriceRange([value, priceRange[1]]);
                        }
                      }}
                      className="mt-1"
                    />
                  </div>
                  <div>
                    <Label htmlFor="max-price">Giá cao nhất</Label>
                    <Input
                      id="max-price"
                      type="number"
                      value={priceRange[1]}
                      onChange={(e) => {
                        const value = parseInt(e.target.value);
                        if (!isNaN(value) && value <= maxPrice && value >= priceRange[0]) {
                          setPriceRange([priceRange[0], value]);
                        }
                      }}
                      className="mt-1"
                    />
                  </div>
                </div>
                <Button 
                  onClick={applyPriceFilter} 
                  className="w-full"
                  variant="outline"
                >
                  <SlidersHorizontal className="mr-2 h-4 w-4" />
                  Áp dụng khoảng giá
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
