import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export default function AboutPage() {
    return (
        <div className="container mx-auto py-10 px-4">
            <h1 className="text-3xl font-bold mb-6">About StationeryShop</h1>
            <Card>
                <CardHeader>
                    <CardTitle>Our Story</CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="mb-4">
                        Founded in 2025, StationeryShop has been passionate about providing high-quality stationery for all your
                        needs. Our journey began with a simple idea: to offer a curated selection of the finest writing instruments,
                        paper products, and office supplies to stationery enthusiasts and professionals alike.
                    </p>
                    <p className="mb-4">
                        At StationeryShop, we believe that the right tools can inspire creativity, boost productivity, and make
                        everyday tasks a joy. That's why we carefully select each item in our inventory, ensuring that it meets our
                        high standards for quality, design, and functionality.
                    </p>
                    <p>
                        Whether you're a student, a professional, or simply someone who appreciates the art of writing, we're here
                        to help you find the perfect stationery items to suit your needs and express your unique style.
                    </p>
                </CardContent>
            </Card>
        </div>
    )
}

