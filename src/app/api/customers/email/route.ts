import { prisma } from "@/lib/prisma"
import { NextResponse } from "next/server"

export async function GET(request: Request) {
  const url = new URL(request.url)
  const email = url.searchParams.get('email')

  const customer = await prisma.user.findUnique({
    where: {
      email: email!
    },
    include: {
      address: true // This includes the full address data
    }
  })

  return NextResponse.json(customer)
}
