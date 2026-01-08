"use client"

import { useEffect, useState } from "react"

const PaymentPage = () => {
  const [paymentMethod, setPaymentMethod] = useState("visa")
  const [loading, setLoading] = useState(false)
  const [cartTotal, setCartTotal] = useState(0)

  useEffect(() => {
    const storedCart = localStorage.getItem('cart')
    if (storedCart) {
      const cartItems = JSON.parse(storedCart)
      const total = cartItems.reduce((sum: number, item: any) =>
          sum + item.price * item.quantity, 0
      )
      setCartTotal(total)
    }
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const method = params.get("method") || "visa"
    setPaymentMethod(method)

    if (method === "visa") {
      window.location.href = "/checkout/payment/visa"
    } else if (method === "VNPAY" && cartTotal > 0) {
      handleVNPayPayment()
    }
  }, [cartTotal]) // Combine the logic into a single useEffect
  
  const handleVNPayPayment = async () => {
    setLoading(true)
    const orderId = `ORDER_${Date.now()}`
    const amount = cartTotal
    const orderInfo = "Payment for order"
    try {
      const cartItems = JSON.parse(localStorage.getItem('cart') || '[]')
      const userDetails = JSON.parse(localStorage.getItem('userDetails') || '{}')
      
      await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cartItems,
          userDetails,
          paymentDetails: {
            amount: cartTotal,
            method: 'VNPAY',
            status: 'PENDING',
          },
        }),
      })

      const response = await fetch("/api/vnpay/generate-payment-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ orderId, amount, orderInfo }),
      })

      if (!response.ok) {
        throw new Error("Network response was not ok")
      }

      const data = await response.json()
      if (data.paymentUrl) {
        console.log("Redirecting to payment URL:", data.paymentUrl)
        window.location.href = data.paymentUrl
      } else {
        console.error("Payment URL not received")
      }
    } catch (error) {
      console.error("Error initiating payment:", error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container mx-auto py-10">
      <h1 className="text-3xl font-bold mb-5">Payment</h1>
      {paymentMethod === "VNPAY" ? (
        <div className="text-center">
          {loading ? <p>Redirecting to VNPay...</p> : <p>Please wait while we redirect you to VNPay.</p>}
        </div>
      ) : (
        <p>Selected payment method: {paymentMethod}</p>
      )}
    </div>
  )
}

export default PaymentPage
