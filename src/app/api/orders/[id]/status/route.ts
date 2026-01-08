import { prisma } from "@/lib/prisma";
import {NextRequest, NextResponse} from "next/server";

export async function PUT(
    request: NextRequest
) {
  const url = new URL(request.url);
  const pathParts = url.pathname.split('/');
  const idFromPath = pathParts[pathParts.indexOf('orders') + 1];
  try {
    const orderId = parseInt(idFromPath);
    if (isNaN(orderId)) {
      return NextResponse.json({ message: "Invalid order ID" }, { status: 400 });
    }

    const { status } = await request.json();
    if (!status || !['PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED'].includes(status)) {
      return NextResponse.json({ message: "Invalid status value" }, { status: 400 });
    }

    // Get the current order status
    const currentOrder = await prisma.order.findUnique({
      where: { id: orderId },
      include: {
        items: {
          include: {
            product: true
          }
        }
      }
    });

    if (!currentOrder) {
      return NextResponse.json({ message: "Order not found" }, { status: 404 });
    }

    // Special handling for cancellation
    if (status === 'CANCELLED') {
      // Only return quantities if the order wasn't already cancelled
      if (currentOrder.status !== 'CANCELLED') {
        // Start a transaction to update the order status and return product quantities
        await prisma.$transaction(async (tx) => {
          // Update each product quantity
          for (const item of currentOrder.items) {
            await tx.product.update({
              where: { id: item.productId },
              data: { quantity: { increment: item.quantity } },
            });
          }

          // Update the order status
          await tx.order.update({
            where: { id: orderId },
            data: { status },
          });
        });

        return NextResponse.json({ 
          message: "Order cancelled and product quantities returned to inventory" 
        });
      }
    }

    // For other status updates, just update the status
    const updatedOrder = await prisma.order.update({
      where: { id: orderId },
      data: { status },
    });

    return NextResponse.json(updatedOrder);
  } catch (error) {
    console.error("Error updating order status:", error);
    return NextResponse.json(
      { message: "Error updating order status" },
      { status: 500 }
    );
  }
}
