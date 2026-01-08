import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

export default function ContactPage() {
    return (
        <div className="container mx-auto py-10 px-4">
            <h1 className="text-3xl font-bold mb-6">Contact Us</h1>
            <div className="grid md:grid-cols-2 gap-6">
                <Card>
                    <CardHeader>
                        <CardTitle>Send us a message</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <form className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="name">Name</Label>
                                <Input id="name" placeholder="Your name" />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="email">Email</Label>
                                <Input id="email" type="email" placeholder="Your email" />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="message">Message</Label>
                                <Textarea id="message" placeholder="Your message" />
                            </div>
                            <Button type="submit">Send Message</Button>
                        </form>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <CardTitle>Contact Information</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="mb-2">
                            <strong>Address:</strong> 806 QL22, ấp Mỹ Hoà 3, Hóc Môn, Hồ Chí Minh, Vietnam
                        </p>
                        <p className="mb-2">
                            <strong>Phone:</strong> (+84) 908 563 838
                        </p>
                        <p className="mb-2">
                            <strong>Email:</strong> 22dh121484@st.huflit.edu.vn
                        </p>
                        <p className="mb-4">
                            <strong>Business Hours:</strong> Monday - Friday, 9am - 5pm
                        </p>
                        <p>
                            We aim to respond to all inquiries within 24 hours during business days. Thank you for your patience and
                            understanding.
                        </p>
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}

