import { useState, useEffect } from 'react'

export type CartItem = {
  id: string
  name: string
  price: number
  quantity: number
  stock: number
}

export function useCart() {
  const [items, setItems] = useState<CartItem[]>([])

  useEffect(() => {
    const storedCart = localStorage.getItem('cart')
    if (storedCart) {
      setItems(JSON.parse(storedCart))
    }
  }, [])

  const addItem = (item: CartItem) => {
    setItems(currentItems => {
      const existingItem = currentItems.find(i => i.id === item.id)
      
      const newItems = existingItem 
        ? currentItems.map(i => 
            i.id === item.id 
              ? { ...i, quantity: i.quantity + item.quantity }
              : i
          )
        : [...currentItems, item]
      
      localStorage.setItem('cart', JSON.stringify(newItems))
      return newItems
    })
    triggerCartUpdate()
  }

  const removeItem = (id: string) => {
    setItems(currentItems => {
      const newItems = currentItems.filter(item => item.id !== id)
      localStorage.setItem('cart', JSON.stringify(newItems))
      return newItems
    })
    triggerCartUpdate()
  }

  const updateQuantity = (id: string, quantity: number) => {
    setItems(currentItems => {
      const newItems = currentItems.map(item =>
        item.id === id ? { ...item, quantity } : item
      )
      localStorage.setItem('cart', JSON.stringify(newItems))
      return newItems
    })
    triggerCartUpdate()
  }

  return {
    items,
    addItem,
    removeItem,
    updateQuantity,
    totalItems: items.reduce((sum, item) => sum + item.quantity, 0)
  }
}
const triggerCartUpdate = () => {
  window.dispatchEvent(new Event('cartUpdated'))
}
