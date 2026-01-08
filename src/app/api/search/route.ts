import { prisma } from '@/lib/prisma'
import { NextResponse } from 'next/server'

// Function to remove diacritics (accents) from text
function removeDiacritics(str: string) {
  return str.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const query = searchParams.get('q')

  if (!query) {
    return NextResponse.json([])
  }

  // First, try to find products with the exact query (with accents)
  const exactProducts = await prisma.product.findMany({
    where: {
      name: {
        contains: query,
        mode: 'insensitive'
      }
    },
    select: {
      id: true,
      name: true,
      price: true,
      quantity: true
    }
  })

  // If we found exact matches, return them
  if (exactProducts.length > 0) {
    return NextResponse.json(exactProducts)
  }

  // If no exact matches, try to find products by removing diacritics
  // Get all products first
  const allProducts = await prisma.product.findMany({
    select: {
      id: true,
      name: true,
      price: true,
      quantity: true
    }
  })

  // Filter products by comparing normalized strings (without diacritics)
  const normalizedQuery = removeDiacritics(query.toLowerCase())
  const filteredProducts = allProducts.filter(product => 
    removeDiacritics(product.name.toLowerCase()).includes(normalizedQuery)
  )

  // Return up to 5 matches
  return NextResponse.json(filteredProducts.slice(0, 5))
}