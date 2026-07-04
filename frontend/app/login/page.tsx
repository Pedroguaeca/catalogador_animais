"use client";

import { signIn, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const MAIN_ROUTE = "/dashboard";

function decodeBase64url(str: string): string {
  const b64 = str.replace(/-/g, "+").replace(/_/g, "/");
  const padded = b64 + "==".slice(0, (4 - (b64.length % 4)) % 4);
  return atob(padded);
}

export default function LoginPage() {
  const { status } = useSession();
  const router = useRouter();
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState<string | null>(null);
  const [loading,  setLoading]  = useState(false);

  useEffect(() => {
    if (status === "authenticated") router.replace(MAIN_ROUTE);
  }, [status, router]);

  const handleCredentials = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const result = await signIn("cognito-credentials", {
      redirect: false,
      email,
      password,
    });

    setLoading(false);

    if (!result) return;

    if (result.error?.startsWith("NEEDS_NEW_PASSWORD:")) {
      const encoded = result.error.slice("NEEDS_NEW_PASSWORD:".length);
      const { session, email: challengeEmail } = JSON.parse(decodeBase64url(encoded));
      sessionStorage.setItem("cognito_challenge_session", session);
      sessionStorage.setItem("cognito_challenge_email",   challengeEmail);
      router.push("/definir-senha");
      return;
    }

    if (result.error) {
      setError("Email ou senha incorretos.");
      return;
    }

    router.replace(MAIN_ROUTE);
  };

  if (status === "loading" || status === "authenticated") {
    return (
      <div style={{
        minHeight: "100vh", display: "flex", alignItems: "center",
        justifyContent: "center", background: "#0D0C0B",
      }}>
        <p style={{ color: "#9A9080", fontSize: 14 }}>A carregar…</p>
      </div>
    );
  }

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center",
      justifyContent: "center", background: "#0D0C0B",
    }}>
      <div style={{
        background: "#1A1916", border: "1px solid #2E2C28", borderRadius: 12,
        padding: "40px 48px", width: 360, display: "flex", flexDirection: "column", gap: 24,
      }}>
        <div>
          <h1 style={{ color: "#F5F0E8", fontSize: 22, fontWeight: 700, margin: 0 }}>SIAB</h1>
          <p style={{ color: "#9A9080", fontSize: 14, margin: "6px 0 0" }}>
            Sistema de Inteligência Ambiental e Biodiversidade
          </p>
        </div>

        {/* Email + senha — em cima */}
        <form onSubmit={handleCredentials} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <input
            type="email" placeholder="Email" value={email}
            onChange={(e) => setEmail(e.target.value)} required
            style={{
              background: "#0D0C0B", color: "#F5F0E8", border: "1px solid #2E2C28",
              borderRadius: 8, padding: "10px 14px", fontSize: 14, outline: "none",
            }}
          />
          <input
            type="password" placeholder="Senha" value={password}
            onChange={(e) => setPassword(e.target.value)} required
            style={{
              background: "#0D0C0B", color: "#F5F0E8", border: "1px solid #2E2C28",
              borderRadius: 8, padding: "10px 14px", fontSize: 14, outline: "none",
            }}
          />
          {error && <p style={{ color: "#FF6B6B", fontSize: 13, margin: 0 }}>{error}</p>}
          <button
            type="submit" disabled={loading}
            style={{
              background: "#3B7A57", color: "#F5F0E8", border: "none", borderRadius: 8,
              padding: "10px 0", fontWeight: 600, cursor: "pointer", fontSize: 15,
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? "Entrando…" : "Entrar"}
          </button>
        </form>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ flex: 1, height: 1, background: "#2E2C28" }} />
          <span style={{ color: "#6B6460", fontSize: 12 }}>ou</span>
          <div style={{ flex: 1, height: 1, background: "#2E2C28" }} />
        </div>

        {/* Google — em baixo, com logo oficial */}
        <button
          onClick={() => signIn("cognito", { callbackUrl: MAIN_ROUTE })}
          style={{
            background: "#F5F0E8", color: "#1A1916", border: "none", borderRadius: 8,
            padding: "10px 0", fontWeight: 600, cursor: "pointer", fontSize: 15,
            display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
          }}
        >
          {/* Google "G" logo — 4 cores oficiais */}
          <svg width="18" height="18" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
            <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.93 2.31-8.16 2.31-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
          </svg>
          Entrar com Google
        </button>

      </div>
    </div>
  );
}
