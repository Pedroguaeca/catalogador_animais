export { default } from "next-auth/middleware";

export const config = {
  matcher: ["/upload/:path*", "/review/:path*", "/export/:path*", "/dashboard/:path*"],
};
