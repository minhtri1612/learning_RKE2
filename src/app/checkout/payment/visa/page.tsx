"use client";

import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { CreditCard } from "lucide-react";

interface VisaPaymentForm {
    cardNumber: string;
    expiryDate: string;
    cvv: string;
    cardHolderName: string;
}

const VISAPaymentPage = () => {
    const [paymentInfo, setPaymentInfo] = useState<VisaPaymentForm>({
        cardNumber: "",
        expiryDate: "",
        cvv: "",
        cardHolderName: "",
    });
    const [cartTotal, setCartTotal] = useState(0);
    const [isFlipped, setIsFlipped] = useState(false);

    useEffect(() => {
        const storedCart = localStorage.getItem("cart");
        if (storedCart) {
            const cartItems = JSON.parse(storedCart);
            const total = cartItems.reduce(
                (sum: number, item: any) => sum + item.price * item.quantity,
                0
            );
            setCartTotal(total);
        }
    }, []);

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value } = e.target;
        let formattedValue = value;

        if (name === "cardNumber") {
            formattedValue = value.replace(/\D/g, "").replace(/(\d{4})/g, "$1 ").trim();
        } else if (name === "expiryDate") {
            formattedValue = value
                .replace(/\D/g, "")
                .replace(/(\d{2})(\d)/, "$1/$2")
                .slice(0, 5);
        } else if (name === "cvv") {
            formattedValue = value.replace(/\D/g, "").slice(0, 3);
        }

        setPaymentInfo({ ...paymentInfo, [name]: formattedValue });
        if (name === "cvv") setIsFlipped(true);
        else setIsFlipped(false);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        toast("Đang xử lý thanh toán", {
            description: "Vui lòng đợi trong giây lát...",
        });

        try {
            // Get cart items and user details
            const cartItems = JSON.parse(localStorage.getItem('cart') || '[]');
            const userDetails = JSON.parse(localStorage.getItem('userDetails') || '{}');
            
            // Create order in database
            const response = await fetch('/api/orders', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cartItems,
                    userDetails,
                    paymentDetails: {
                        amount: cartTotal,
                        method: 'VISA',
                        status: 'COMPLETED',
                    },
                }),
            });
            
            if (!response.ok) {
                throw new Error('Failed to create order');
            }
            
            await new Promise((resolve) => setTimeout(resolve, 2000));
            
            // Clear the cart after successful payment
            localStorage.removeItem('cart');
            
            toast.success("Thanh toán thành công", {
                description: "Đơn hàng của bạn đã được xác nhận",
            });
            window.location.href = "/checkout/confirmation";
        } catch (error) {
            console.error("Payment error:", error);
            toast.error("Lỗi thanh toán", {
                description: "Vui lòng kiểm tra lại thông tin thẻ",
            });
        }
    };

    return (
        <div className="container mx-auto px-4 py-12 max-w-2xl">
            <h1 className="text-4xl font-bold text-center mb-8 bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                Thanh Toán Bằng Visa
            </h1>

            {/* Card Preview */}
            <div className="relative mb-10 h-56 w-full max-w-md mx-auto perspective-1000">
                <div
                    className={`absolute inset-0 transition-transform duration-500 [transform-style:preserve-3d] ${
                        isFlipped ? "rotate-y-180" : ""
                    }`}
                >
                    {/* Front of Card */}
                    <div className="absolute inset-0 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-xl shadow-lg p-6 text-white [backface-visibility:hidden]">
                        <div className="flex justify-between items-center mb-6">
                            <CreditCard size={32} />
                            <span className="text-xl font-semibold">VISA</span>
                        </div>
                        <div className="text-2xl tracking-wider mb-6">
                            {paymentInfo.cardNumber || "4242 4242 4242 4242"}
                        </div>
                        <div className="flex justify-between">
                            <div>
                                <Label className="text-xs text-gray-200">Tên Chủ Thẻ</Label>
                                <p className="uppercase">
                                    {paymentInfo.cardHolderName || "NGUYEN VAN A"}
                                </p>
                            </div>
                            <div>
                                <Label className="text-xs text-gray-200">Hết Hạn</Label>
                                <p>{paymentInfo.expiryDate || "MM/YY"}</p>
                            </div>
                        </div>
                    </div>

                    {/* Back of Card */}
                    <div className="absolute inset-0 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-xl shadow-lg [backface-visibility:hidden] [transform:rotateY(180deg)]">
                        <div className="h-10 bg-black mt-6" />
                        <div className="p-6">
                            <Label className="text-xs text-gray-200">CVV</Label>
                            <div className="bg-white text-black rounded px-4 py-2 mt-2 w-20 text-center">
                                {paymentInfo.cvv || "123"}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Payment Form */}
            <form
                onSubmit={handleSubmit}
                className="bg-white rounded-xl shadow-md p-6 space-y-6"
            >
                <div>
                    <Label htmlFor="cardHolderName" className="text-gray-700">
                        Tên Chủ Thẻ
                    </Label>
                    <Input
                        id="cardHolderName"
                        name="cardHolderName"
                        value={paymentInfo.cardHolderName}
                        onChange={handleInputChange}
                        placeholder="NGUYEN VAN A"
                        className="mt-1 focus:ring-2 focus:ring-blue-500 transition-all"
                        required
                    />
                </div>

                <div>
                    <Label htmlFor="cardNumber" className="text-gray-700">
                        Số Thẻ
                    </Label>
                    <Input
                        id="cardNumber"
                        name="cardNumber"
                        value={paymentInfo.cardNumber}
                        onChange={handleInputChange}
                        placeholder="4242 4242 4242 4242"
                        maxLength={19}
                        className="mt-1 focus:ring-2 focus:ring-blue-500 transition-all"
                        required
                    />
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <Label htmlFor="expiryDate" className="text-gray-700">
                            Ngày Hết Hạn
                        </Label>
                        <Input
                            id="expiryDate"
                            name="expiryDate"
                            value={paymentInfo.expiryDate}
                            onChange={handleInputChange}
                            placeholder="MM/YY"
                            className="mt-1 focus:ring-2 focus:ring-blue-500 transition-all"
                            required
                        />
                    </div>
                    <div>
                        <Label htmlFor="cvv" className="text-gray-700">
                            Mã CVV
                        </Label>
                        <Input
                            id="cvv"
                            name="cvv"
                            type="password"
                            value={paymentInfo.cvv}
                            onChange={handleInputChange}
                            placeholder="123"
                            className="mt-1 focus:ring-2 focus:ring-blue-500 transition-all"
                            required
                        />
                    </div>
                </div>

                <div className="border-t pt-4">
                    <p className="text-lg font-semibold text-gray-800 mb-4">
                        Tổng thanh toán:{" "}
                        <span className="text-blue-600">
              {new Intl.NumberFormat("vi-VN", {
                  style: "currency",
                  currency: "VND",
              }).format(cartTotal)}
            </span>
                    </p>
                    <Button
                        type="submit"
                        className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 transition-all duration-300"
                    >
                        Xác Nhận Thanh Toán
                    </Button>
                </div>
            </form>
        </div>
    );
};

export default VISAPaymentPage;