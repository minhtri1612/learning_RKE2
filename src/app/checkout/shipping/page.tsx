"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {toast} from "sonner";

export default function ShippingPage() {
  const router = useRouter()
  const [formData, setFormData] = useState({
    fullName: "",
    email: "",
    gender: "",
    dateOfBirth: "",
    street: "",
    ward: "",
    district: "",
    city: "",
    country: "",
    apartment: "",
  })
  const [paymentMethod, setPaymentMethod] = useState("visa")

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value })
  }

  const handleGenderChange = (value: string) => {
    setFormData({ ...formData, gender: value })
  }
  const handleEmailChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const email = e.target.value
    setFormData({ ...formData, email })

    if (email) {
      const response = await fetch(`/api/customers/email?email=${email}`)
      const customer = await response.json()

      if (customer) {
        setFormData({
          ...formData,
          email,
          fullName: customer.fullName,
          gender: customer.gender,
          dateOfBirth: customer.dateOfBirth,
          street: customer.address.street,
          ward: customer.address.ward,
          district: customer.address.district,
          city: customer.address.city,
          country: customer.address.country,
          apartment: customer.address.apartment
        })
        toast.success("Thông tin khách hàng", {
          description: "Đã tự động điền thông tin từ tài khoản của bạn"
        })
      }
    }
  }
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    localStorage.setItem('userDetails', JSON.stringify(formData))

    if (paymentMethod === "cod") {
      const cartItems = JSON.parse(localStorage.getItem('cart') || '[]')
      const total = cartItems.reduce((sum: number, item: any) => sum + item.price * item.quantity, 0)

      await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cartItems,
          userDetails: formData,
          paymentDetails: { amount: total, method: 'COD', status: 'PENDING' }
        })
      })
      router.push("/checkout/confirmation")
    } else if (paymentMethod === "VNPAY") {
      router.push("/checkout/payment?method=VNPAY")
    } else {
      router.push("/checkout/payment?method=visa")
    }
  }

  return (
      <div className="container mx-auto px-4 py-10 max-w-2xl">
        <h1 className="text-3xl font-bold mb-8 text-center">Thông Tin Giao Hàng</h1>

        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Personal Information Section */}
          <section className="space-y-4">
            <h2 className="text-xl font-semibold">Thông tin cá nhân</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="fullName">Họ và tên</Label>
                <Input id="fullName" name="fullName" value={formData.fullName} onChange={handleChange} required />
              </div>
              <div>
                <Label htmlFor="email">Email</Label>
                <Input
                    id="email"
                    name="email"
                    type="email"
                    value={formData.email}
                    onChange={handleEmailChange}
                    required
                />
              </div>
              <div>
                <Label htmlFor="gender">Giới tính</Label>
                <Select onValueChange={handleGenderChange} defaultValue={formData.gender}>
                  <SelectTrigger>
                    <SelectValue placeholder="Chọn giới tính" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Male">Nam</SelectItem>
                    <SelectItem value="Female">Nữ</SelectItem>
                    <SelectItem value="Other">Khác</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="dateOfBirth">Ngày sinh</Label>
                <Input id="dateOfBirth" name="dateOfBirth" type="date" value={formData.dateOfBirth} onChange={handleChange} />
              </div>
            </div>
          </section>

          {/* Shipping Address Section */}
          <section className="space-y-4">
            <h2 className="text-xl font-semibold">Địa chỉ giao hàng</h2>
            <div className="space-y-4">
              <div>
                <Label htmlFor="street">Đường</Label>
                <Input id="street" name="street" value={formData.street} onChange={handleChange} required />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="ward">Phường/Xã</Label>
                  <Input id="ward" name="ward" value={formData.ward} onChange={handleChange} />
                </div>
                <div>
                  <Label htmlFor="district">Quận/Huyện</Label>
                  <Input id="district" name="district" value={formData.district} onChange={handleChange} />
                </div>
                <div>
                  <Label htmlFor="city">Thành Phố/Tỉnh</Label>
                  <Input id="city" name="city" value={formData.city} onChange={handleChange} required />
                </div>
                <div>
                  <Label htmlFor="country">Quốc Gia</Label>
                  <Input id="country" name="country" value={formData.country} onChange={handleChange} required />
                </div>
              </div>
              <div>
                <Label htmlFor="apartment">Số Nhà/Căn Hộ (Không bắt buộc)</Label>
                <Input id="apartment" name="apartment" value={formData.apartment} onChange={handleChange} />
              </div>
            </div>
          </section>

          {/* Payment Method Section */}
          <section className="space-y-4">
            <h2 className="text-xl font-semibold">Phương Thức Thanh Toán</h2>
            <RadioGroup
                defaultValue="visa"
                onValueChange={setPaymentMethod}
                className=" gap-4"
            >
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="visa" id="visa" />
                <Label htmlFor="visa">Visa</Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="VNPAY" id="VNPAY" />
                <Label htmlFor="VNPAY">VNPAY</Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="cod" id="cod" />
                <Label htmlFor="cod">Thanh Toán Khi Nhận Hàng</Label>
              </div>
            </RadioGroup>
          </section>

          {/* Submit Button */}
          <div className="pt-4">
            <Button type="submit" className="w-full">Tiếp Tục Thanh Toán</Button>
          </div>
        </form>
      </div>
  )
}