import Link from 'next/link'

export default function Footer() {
  return (
    <footer className="bg-gray-100 mt-8">
      <div className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div>
            <h3 className="text-lg font-semibold mb-4">About Us</h3>
            <p className="text-sm text-gray-600">
              We are passionate about providing high-quality stationery for all your needs.
            </p>
          </div>
          <div>
            <h3 className="text-lg font-semibold mb-4">Quick Links</h3>
            <ul className="space-y-2">
              <li><Link href="/about" className="text-sm text-gray-600 hover:text-gray-900">About</Link></li>
              <li><Link href="/contact" className="text-sm text-gray-600 hover:text-gray-900">Contact</Link></li>
              <li><Link href="/faq" className="text-sm text-gray-600 hover:text-gray-900">FAQ</Link></li>
            </ul>
          </div>
          <div>
            <h3 className="text-lg font-semibold mb-4">Contact Us</h3>
            <p className="text-sm text-gray-600">
              Email: 22dh121484@st.huflit.edu.vn<br />
              Phone: (+84) 908 563 838<br />
              Address: 806 QL22, ấp Mỹ Hoà 3, Hóc Môn, Hồ Chí Minh, Vietnam
            </p>
          </div>
        </div>
        <div className="mt-8 pt-8 border-t border-gray-200 text-center">
          <p className="text-sm text-gray-600">
            © 2025 StationeryShop. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  )
}

