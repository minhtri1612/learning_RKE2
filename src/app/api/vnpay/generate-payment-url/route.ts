// app/api/vnpay/generate-payment-url/route.ts
import { NextResponse } from 'next/server';
import { VNPay, ProductCode, VnpLocale, dateFormat } from 'vnpay';

const vnp = new VNPay({
  tmnCode: process.env.VNP_TMN_CODE as string,
  secureSecret: process.env.VNP_HASH_SECRET as string,
  vnpayHost: 'https://sandbox.vnpayment.vn/paymentv2/vpcpay.html',
  testMode : true
});

export async function POST(request: Request) {
  try {
    const { orderId, amount, orderInfo } = await request.json();
    const clientIp = request.headers.get('x-forwarded-for') || '127.0.0.1';

    console.log("Received payment request:", { orderId, amount, orderInfo });

    // // Log environment variables for debugging
    // console.log("VNP_TMN_CODE:", process.env.VNP_TMN_CODE);
    // console.log("VNP_HASH_SECRET:", process.env.VNP_HASH_SECRET);

    const paymentUrl = vnp.buildPaymentUrl({
      vnp_Amount: amount, // Convert to VNPay format
      vnp_IpAddr: clientIp as string,
      vnp_TxnRef: orderId,
      vnp_OrderInfo: orderInfo,
      vnp_OrderType: ProductCode.Other,
      vnp_ReturnUrl: 'https://meostationery.netlify.app/checkout/payment/vnpay', 
      vnp_Locale: VnpLocale.VN,
      vnp_CreateDate: dateFormat(new Date()),
      vnp_ExpireDate: dateFormat(new Date(Date.now() + 60 * 60 * 60 * 1000)),
    });

    console.log("Generated VNPay Payment URL:", paymentUrl);
    return NextResponse.json({ paymentUrl });
  } catch (error) {
    console.error('Error generating VNPAY URL:', error);
    return NextResponse.json(
      { error: 'Failed to generate payment URL' },
      { status: 500 }
    );
  }
}