"use client";

import Link from 'next/link'
import Image from 'next/image'
import { Button } from '@/components/ui/button'
import { ShoppingBag, Home, ArrowRight } from 'lucide-react'
import { useEffect } from 'react'

export default function ConfirmationPage() {
    // Ensure cart is cleared on this page as a backup
    useEffect(() => {
        // Double-check that the cart is cleared
        if (localStorage.getItem('cart')) {
            localStorage.removeItem('cart');
        }
    }, []);

    return (
        <div className="container mx-auto py-10 px-4 max-w-3xl">
            <div className="bg-white rounded-lg shadow-lg p-8 text-center">
                <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
                    <ShoppingBag className="h-10 w-10 text-green-600" />
                </div>
                
                <h1 className="text-3xl font-bold mb-3 text-gray-800">Đặt Hàng Thành Công!</h1>
                <p className="text-gray-600 mb-6">Cảm ơn bạn đã mua hàng. Đơn hàng của bạn đã được xác nhận và đang được xử lý.</p>
                
                <div className="flex justify-center mb-8">
                    <Image
                        src="/test.jpg"
                        alt="Order Success"
                        width={300}
                        height={300}
                        className="animate-bounce rounded-lg object-contain"
                    />
                </div>
                
                <div className="flex flex-col sm:flex-row gap-4 justify-center">
                    <Link href="/" className="w-full sm:w-auto">
                        <Button variant="outline" className="w-full">
                            <Home className="mr-2 h-4 w-4" />
                            Quay Về Trang Chủ
                        </Button>
                    </Link>
                    <Link href="/products" className="w-full sm:w-auto">
                        <Button className="w-full bg-gradient-to-r from-blue-600 to-indigo-600">
                            Tiếp Tục Mua Sắm
                            <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                    </Link>
                </div>
            </div>
        </div>
    )
}
