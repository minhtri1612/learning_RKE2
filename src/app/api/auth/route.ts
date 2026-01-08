import { NextResponse } from 'next/server'
import bcrypt from 'bcrypt'

const ADMIN_PASSWORD_HASH = '$2b$10$XOh6SqVurvs0ejClg3Ydseu6ekOoqxmPkFKIwh9dDwZgz6syf//i.' 

export async function POST(request: Request) {
    const { username, password } = await request.json()

    if (username === 'admin') {
        const isValidPassword = await bcrypt.compare(password, ADMIN_PASSWORD_HASH)

        if (isValidPassword) {
            return NextResponse.json({ success: true })
        }
    }

    return NextResponse.json({ success: false }, { status: 401 })
}
