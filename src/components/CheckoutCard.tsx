"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"

export function CheckoutCard() {
  const router = useRouter()
  const [formData, setFormData] = useState({
    cardNumber: "",
    cardName: "",
    expiryDate: "",
    cvv: "",
  })

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // Handle payment processing here
    console.log("Processing payment:", formData)
    // Simulate successful payment
    setTimeout(() => {
      router.push("/checkout/confirmation")
    }, 1000)
  }

  return (
    <Card className="w-full max-w-md mx-auto">
      <CardHeader>
        <CardTitle>Payment Details</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit}>
          <div className="grid w-full items-center gap-4">
            <div className="flex flex-col space-y-1.5">
              <Label htmlFor="cardNumber">Card Number</Label>
              <Input
                id="cardNumber"
                name="cardNumber"
                placeholder="1234 5678 9012 3456"
                value={formData.cardNumber}
                onChange={handleChange}
                required
              />
            </div>
            <div className="flex flex-col space-y-1.5">
              <Label htmlFor="cardName">Name on Card</Label>
              <Input
                id="cardName"
                name="cardName"
                placeholder="John Doe"
                value={formData.cardName}
                onChange={handleChange}
                required
              />
            </div>
            <div className="flex gap-4">
              <div className="flex flex-col space-y-1.5 flex-1">
                <Label htmlFor="expiryDate">Expiry Date</Label>
                <Input
                  id="expiryDate"
                  name="expiryDate"
                  placeholder="MM/YY"
                  value={formData.expiryDate}
                  onChange={handleChange}
                  required
                />
              </div>
              <div className="flex flex-col space-y-1.5 flex-1">
                <Label htmlFor="cvv">CVV</Label>
                <Input id="cvv" name="cvv" placeholder="123" value={formData.cvv} onChange={handleChange} required />
              </div>
            </div>
          </div>
        </form>
      </CardContent>
      <CardFooter>
        <Button className="w-full" onClick={handleSubmit}>
          Pay Now
        </Button>
      </CardFooter>
    </Card>
  )
}

