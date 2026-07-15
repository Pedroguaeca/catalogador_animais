"use client";
import { SessionProvider, useSession } from "next-auth/react";
import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";

// Se a renovação silenciosa do idToken falhar (refresh_token expirado/revogado),
// authOptions.ts marca session.error — aqui a gente detecta isso globalmente e
// manda para /login com uma mensagem clara, em vez de deixar cada página
// quebrar sozinha com 401 sem explicação.
function SessionErrorWatcher() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: session } = useSession() as { data: any };
  const router   = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (session?.error === "RefreshAccessTokenError" && pathname !== "/login") {
      router.replace("/login?expired=1");
    }
  }, [session, pathname, router]);

  return null;
}

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <SessionErrorWatcher />
      {children}
    </SessionProvider>
  );
}
