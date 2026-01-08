import { prisma } from "@/lib/prisma";
import { NextResponse } from "next/server";

// Create a simple in-memory store to track recent order attempts
// This helps prevent duplicate orders from the same user in quick succession
const recentOrderAttempts = new Map<string, number>();
const DEBOUNCE_TIME_MS = 5000; // 5 seconds debounce time

export async function POST(request: Request) {
  const { cartItems, userDetails, paymentDetails } = await request.json();

  try {
    // Create a unique key for this order attempt based on user email and cart contents
    const orderKey = `${userDetails.email}-${JSON.stringify(cartItems)}`;
    const now = Date.now();
    
    // Check if this is a duplicate order attempt within the debounce window
    if (recentOrderAttempts.has(orderKey)) {
      const lastAttempt = recentOrderAttempts.get(orderKey) || 0;
      if (now - lastAttempt < DEBOUNCE_TIME_MS) {
        console.log(`Duplicate order attempt detected for ${orderKey}, ignoring`);
        return NextResponse.json({ 
          success: false, 
          error: "Please wait before submitting another order" 
        }, { status: 429 });
      }
    }
    
    // Update the timestamp for this order attempt
    recentOrderAttempts.set(orderKey, now);
    
    // Clean up old entries from the map to prevent memory leaks
    for (const [key, timestamp] of recentOrderAttempts.entries()) {
      if (now - timestamp > DEBOUNCE_TIME_MS * 2) {
        recentOrderAttempts.delete(key);
      }
    }

    // First check if user exists
    let user = await prisma.user.findUnique({
      where: { email: userDetails.email }
    });

    if (!user) {
      // Create new user if doesn't exist
      const address = await prisma.address.create({
        data: {
          street: userDetails.street,
          ward: userDetails.ward,
          district: userDetails.district,
          city: userDetails.city,
          country: userDetails.country,
          apartment: userDetails.apartment,
        },
      });

      user = await prisma.user.create({
        data: {
          fullName: userDetails.fullName,
          email: userDetails.email,
          gender: userDetails.gender,
          dateOfBirth: userDetails.dateOfBirth,
          addressId: address.id,
        },
      });
    }

    // Create order with existing or new user
    const order = await prisma.$transaction(async (tx) => {
      for (const item of cartItems) {
        await tx.product.update({
          where: { id: item.id },
          data: { quantity: { decrement: item.quantity } },
        });
      }

      const newOrder = await tx.order.create({
        data: {
          userId: user.id,
          status: "PENDING",
          createdAt: new Date().toISOString(),
          items: {
            createMany: {
              data: cartItems.map((item: any) => ({
                productId: item.id,
                quantity: item.quantity,
              })),
            },
          },
        },
      });

      await tx.payment.create({
        data: {
          orderId: newOrder.id,
          amount: paymentDetails.amount,
          method: paymentDetails.method,
          status: paymentDetails.status,
          createdAt: new Date().toISOString(),
        },
      });

      return newOrder;
    });

    return NextResponse.json({ success: true, data: { order, user } });

  } catch (error) {
    console.error("Order creation error:", error instanceof Error ? error.message : String(error));
    return NextResponse.json(
        { success: false, error: "Failed to create order", details: error instanceof Error ? error.message : "Unknown error" },
        { status: 500 }
    );
  }
}

export async function GET(request: Request) {
  try {
    const orders = await prisma.order.findMany({
      include: {
        user: {
          select: {
            fullName: true,
            email: true,
            address: true, // Include address information
          },
        },
        payment: {
          select: {
            amount: true,
          },
        },
        items: {
          include: {
            product: true
          }
        }
      },
      orderBy: {
        createdAt: 'desc',
      },
    });

    return NextResponse.json({
      success: true,
      orders
    });

  } catch (error) {
    console.error('Failed to fetch orders:', error);
    return NextResponse.json(
        { success: false, error: "Failed to fetch orders" },
        { status: 500 }
    );
  }
}