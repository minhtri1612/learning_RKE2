"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ShoppingCart, Check, Minus, Plus } from "lucide-react";
import { toast } from "sonner";
import { Product } from "@prisma/client";
import { useCart } from "@/hooks/useCart";

interface AddToCartButtonProps {
  product: Product;
  variant?: "default" | "outline" | "secondary" | "ghost" | "link" | "destructive";
  size?: "default" | "sm" | "lg" | "icon";
  showQuantity?: boolean;
  className?: string;
  disabled?: boolean;
}

export default function AddToCartButton({
  product,
  variant = "default",
  size = "default",
  showQuantity = false,
  className = "",
  disabled = false
}: AddToCartButtonProps) {
  const { addItem, items } = useCart();
  const [quantity, setQuantity] = useState(1);
  const [isAdding, setIsAdding] = useState(false);

  // Check if the product is already in the cart
  const existingItem = items.find(item => item.id === product.id);
  const isInCart = !!existingItem;

  // Handle adding to cart
  const handleAddToCart = () => {
    if (disabled) return;
    
    setIsAdding(true);
    
    // Add to cart with animation
    setTimeout(() => {
      addItem({
        id: product.id,
        name: product.name,
        price: product.price,
        quantity: quantity,
        stock: product.quantity
      });
      
      toast.success("Đã thêm vào giỏ hàng", {
        description: `${product.name} (${quantity} sản phẩm)`
      });
      
      setIsAdding(false);
      setQuantity(1);
    }, 500);
  };

  const incrementQuantity = () => {
    if (quantity < product.quantity) {
      setQuantity(q => q + 1);
    }
  };

  const decrementQuantity = () => {
    if (quantity > 1) {
      setQuantity(q => q - 1);
    }
  };

  if (showQuantity) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Button 
            type="button" 
            size="icon" 
            variant="outline" 
            onClick={decrementQuantity}
            disabled={quantity <= 1 || disabled}
          >
            <Minus className="h-4 w-4" />
          </Button>
          <span className="w-8 text-center">{quantity}</span>
          <Button 
            type="button" 
            size="icon" 
            variant="outline" 
            onClick={incrementQuantity}
            disabled={quantity >= product.quantity || disabled}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <Button 
          onClick={handleAddToCart}
          variant={variant}
          size={size}
          className={className}
          disabled={disabled || isAdding || product.quantity === 0}
        >
          {isAdding ? (
            <Check className="mr-2 h-4 w-4" />
          ) : (
            <ShoppingCart className="mr-2 h-4 w-4" />
          )}
          {isAdding ? "Đã thêm" : "Thêm vào giỏ hàng"}
        </Button>
      </div>
    );
  }

  return (
    <Button 
      onClick={handleAddToCart}
      variant={variant}
      size={size}
      className={className}
      disabled={disabled || isAdding || product.quantity === 0}
    >
      {isAdding ? (
        <Check className="mr-2 h-4 w-4" />
      ) : (
        <ShoppingCart className="mr-2 h-4 w-4" />
      )}
      {isAdding ? "Đã thêm" : "Thêm vào giỏ hàng"}
    </Button>
  );
}
