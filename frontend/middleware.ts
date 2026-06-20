import createMiddleware from "next-intl/middleware"
import { locales, defaultLocale } from "./i18n.config"
import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

// Segments that should bypass the auth gate. With [locale] routing these
// appear as the LAST path segment (e.g. /en/login → segment "login").
const PUBLIC_SEGMENTS = new Set(["login", "register", "consumer", "report", "check"])
const PUBLIC_PREFIXES = ["/api", "/_next", "/favicon.ico"]

const handleI18nRouting = createMiddleware({
  locales,
  defaultLocale,
})

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  const segments = pathname.split("/").filter(Boolean)

  // Let next-intl handle the locale prefix on every request first.
  const i18nResponse = handleI18nRouting(request)

  // Allow API/internal Next.js paths without auth.
  if (PUBLIC_PREFIXES.some((p) => pathname.startsWith(p)) || segments.length === 0) {
    return i18nResponse
  }

  const lastSegment = segments[segments.length - 1]
  const isPublicPage =
    PUBLIC_SEGMENTS.has(lastSegment) || PUBLIC_SEGMENTS.has(segments[0])

  if (isPublicPage) {
    return i18nResponse
  }

  // Auth gate: check the non-sensitive ts_session indicator cookie.
  // The actual access token is in an httpOnly cookie (not JS-readable).
  const sessionCookie = request.cookies.get("ts_session")?.value

  if (!sessionCookie) {
    const locale = request.cookies.get("NEXT_LOCALE")?.value || defaultLocale
    const loginUrl = new URL(`/${locale}/login`, request.url)
    loginUrl.searchParams.set("callbackUrl", pathname)
    return NextResponse.redirect(loginUrl)
  }

  return i18nResponse
}

export const config = {
  matcher: ["/((?!api|_next|.*\\..*).*)"],
}
