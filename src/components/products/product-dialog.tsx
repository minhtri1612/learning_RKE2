import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import React from "react";

type ProductDialogProps = {
  isEdit?: boolean
  formData: {
    name: string
    price: string
    quantity: string
    description: string
  }
  onInputChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void
  onSubmit: () => void
}

export function ProductDialog({ 
  isEdit = false, 
  formData,
  onInputChange,
  onSubmit 
}: ProductDialogProps) {
  return (
    <DialogContent className="sm:max-w-[425px]" onInteractOutside={e => e.preventDefault()}>
      <DialogHeader>
        <DialogTitle>{isEdit ? 'Edit Product' : 'Add New Product'}</DialogTitle>
        <DialogDescription>
          {isEdit ? 'Make changes to the product here.' : 'Enter the details of the new product here.'}
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-4 py-4">
        <div className="grid grid-cols-4 items-center gap-4">
          <Label htmlFor="name" className="text-right">Name</Label>
          <Input
            id="name"
            name="name"
            value={formData.name}
            onChange={onInputChange}
            className="col-span-3"
          />
        </div>
        <div className="grid grid-cols-4 items-center gap-4">
          <Label htmlFor="price" className="text-right">Price</Label>
          <Input
            id="price"
            name="price"
            type="number"
            value={formData.price}
            onChange={onInputChange}
            className="col-span-3"
          />
        </div>
        <div className="grid grid-cols-4 items-center gap-4">
          <Label htmlFor="quantity" className="text-right">Quantity</Label>
          <Input
              id="quantity"
              name="quantity"
              type="number"
              value={formData.quantity}
              onChange={onInputChange}
              className="col-span-3"
          />
        </div>
        <div className="grid grid-cols-4 items-center gap-4">
          <Label htmlFor="description" className="text-right">Description</Label>
          <Textarea
            id="description"
            name="description"
            value={formData.description}
            onChange={onInputChange}
            className="col-span-3"
          />
        </div>
      </div>
      <DialogFooter>
        <Button type="submit" onClick={onSubmit}>
          {isEdit ? 'Save Changes' : 'Add Product'}
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
