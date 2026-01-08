import { prisma } from "@/lib/prisma";
import { NextResponse } from "next/server";

// Define types for raw query results
interface PriceStats {
  min: number;
  max: number;
}

// GET /api/products
export async function GET(request: Request) {
  const url = new URL(request.url);
  const id = url.searchParams.get('id');
  const search = url.searchParams.get('search');
  const sort = url.searchParams.get('sort');
  const minPrice = url.searchParams.get('minPrice');
  const maxPrice = url.searchParams.get('maxPrice');
  const take = url.searchParams.get('take');
  // If an ID is provided, return a single product
  if (id) {
    const product = await prisma.product.findUnique({
      where: {
        id: id
      }
    });
    return NextResponse.json(product);
  }

  // Build the query for filtering products
  let where: any = {};
  let orderBy: any = { createdAt: 'desc' }; // Default sort by newest

  // Apply search filter
  if (search) {
    const decodedSearch = decodeURIComponent(search)
    where.OR = [
      {
        name: {
          contains: decodedSearch,
          mode: 'insensitive'
        }
      },
      {
        description: {
          contains: decodedSearch,
          mode: 'insensitive'
        }
      }
    ]
  }

  // Apply price filters
  if (minPrice || maxPrice) {
    where.price = {};
    if (minPrice) where.price.gte = parseInt(minPrice);
    if (maxPrice) where.price.lte = parseInt(maxPrice);
  }

  // Apply sorting
  if (sort) {
    if (sort === 'price-asc') {
      orderBy = { price: 'asc' };
    } else if (sort === 'price-desc') {
      orderBy = { price: 'desc' };
    } else if (sort === 'newest') {
      orderBy = { createdAt: 'desc' };
    }
  }
  
  // Get price range for filters
  const priceStats = await prisma.$queryRaw<PriceStats[]>`
    SELECT MIN(price) as "min", MAX(price) as "max" FROM "Product"
  `;

  // Fetch filtered products
  const products = await prisma.product.findMany({
    where,
    orderBy,
    take: take ? parseInt(take) : undefined
  });

  return NextResponse.json({
    products,
    priceRange: {
      min: priceStats[0]?.min || 0,
      max: priceStats[0]?.max || 1000000
    }
  });
}

// POST /api/products
export async function POST(request: Request) {
  const data = await request.json();
  const product = await prisma.product.create({
    data
  });
  return NextResponse.json(product);
}

// PUT /api/products/:id
export async function PUT(request: Request) {
  const url = new URL(request.url);
  const id = url.searchParams.get('id');
  const data = await request.json();

  const parsedData = {
    ...data,
    price: parseInt(data.price),
    quantity: parseInt(data.quantity)
  };
  
  if (!id) {
    return NextResponse.json({ error: 'Product ID is required' }, { status: 400 });
  }

  const product = await prisma.product.update({
    where: { id },
    data: parsedData
  });

  return NextResponse.json(product);
}

// DELETE /api/products/:id
export async function DELETE(request: Request) {
  const url = new URL(request.url);
  const id = url.searchParams.get('id');

  if (!id) {
    return NextResponse.json({ error: 'Product ID is required' }, { status: 400 });
  }

  await prisma.product.delete({
    where: { id }
  });

  return NextResponse.json({ success: true });
}