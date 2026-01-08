import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export default function FAQPage() {
    const faqs = [
        {
            question: "What payment methods do you accept?",
            answer:
                "We accept Visa, MasterCard, VNPay. We also offer cash on delivery for certain locations.",
        },
        {
            question: "How long does shipping take?",
            answer:
                "Shipping times vary depending on your location. Typically, domestic orders are delivered within 3-5 business days, while international orders may take 7-14 business days.",
        },
        {
            question: "Do you offer returns or exchanges?",
            answer:
                "Yes, we offer a 30-day return policy for most items. Products must be unused and in their original packaging. Please contact our customer service team to initiate a return or exchange.",
        },
        {
            question: "Are your products eco-friendly?",
            answer:
                "We strive to offer eco-friendly options whenever possible. Many of our paper products are made from recycled materials, and we offer refillable writing instruments to reduce waste.",
        },
        {
            question: "Do you offer bulk or wholesale pricing?",
            answer:
                "Yes, we offer special pricing for bulk orders and wholesale customers. Please contact our sales team for more information and to discuss your specific needs.",
        },
    ]

    return (
        <div className="container mx-auto py-10 px-4">
            <h1 className="text-3xl font-bold mb-6">Frequently Asked Questions</h1>
            <Card>
                <CardHeader>
                    <CardTitle>Common Questions</CardTitle>
                </CardHeader>
                <CardContent>
                    <Accordion type="single" collapsible className="w-full">
                        {faqs.map((faq, index) => (
                            <AccordionItem key={index} value={`item-${index}`}>
                                <AccordionTrigger>{faq.question}</AccordionTrigger>
                                <AccordionContent>{faq.answer}</AccordionContent>
                            </AccordionItem>
                        ))}
                    </Accordion>
                </CardContent>
            </Card>
        </div>
    )
}

