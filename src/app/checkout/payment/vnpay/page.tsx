"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import { toast } from "sonner";

const VNPayReturnPageContent = () => {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [status, setStatus] = useState("Đang xử lý thanh toán...");

  useEffect(() => {
    console.log("Raw search params:", searchParams.toString());

    const responseCode = searchParams.get("vnp_ResponseCode");
    console.log("VNPay Response Code:", responseCode); // Debugging log

    if (responseCode === "00") {
      // Payment successful
      setStatus("Thanh toán thành công! Cảm ơn bạn.");
      
      // Clear the cart after successful payment
      localStorage.removeItem('cart');
      
      // Show success toast
      toast.success("Thanh toán thành công", {
        description: "Đơn hàng của bạn đã được xác nhận",
      });
      
      // Redirect to confirmation page after a short delay
      setTimeout(() => {
        router.push('/checkout/confirmation');
      }, 2000);
    } else {
      // Payment failed
      setStatus("Thanh toán thất bại. Vui lòng thử lại.");
      
      // Show error toast
      toast.error("Lỗi thanh toán", {
        description: "Vui lòng thử lại hoặc chọn phương thức thanh toán khác",
      });
      
      // Redirect back to payment page after a short delay
      setTimeout(() => {
        router.push('/checkout/payment');
      }, 3000);
    }
  }, [searchParams, router]);

  return (
    <div className="container mx-auto py-10 text-center">
      <h1 className="text-3xl font-bold mb-5">{status}</h1>
      <p className="text-gray-600">Bạn sẽ được chuyển hướng tự động...</p>
    </div>
  );
};

export default function VNPayReturnPage() {
  return (
    <Suspense fallback={<div>Đang tải...</div>}>
      <VNPayReturnPageContent />
    </Suspense>
  );
}
