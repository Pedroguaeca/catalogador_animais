"use client";

import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const MAIN_ROUTE = "/dashboard";

const inputStyle: React.CSSProperties = {
  background: "#0D0C0B", color: "#F5F0E8", border: "1px solid #2E2C28",
  borderRadius: 8, padding: "10px 14px", fontSize: 14, outline: "none",
  width: "100%", boxSizing: "border-box",
};

export default function DefinirSenhaPage() {
  const router = useRouter();
  const [email,          setEmail]          = useState("");
  const [cognitoSession, setCognitoSession] = useState("");
  const [newPassword,    setNewPassword]    = useState("");
  const [confirm,        setConfirm]        = useState("");
  const [error,          setError]          = useState<string | null>(null);
  const [loading,        setLoading]        = useState(false);

  // Read challenge state from sessionStorage — if missing, the user
  // landed here directly (not via the challenge redirect) so send back.
  useEffect(() => {
    const session     = sessionStorage.getItem("cognito_challenge_session");
    const storedEmail = sessionStorage.getItem("cognito_challenge_email");
    if (!session || !storedEmail) {
      router.replace("/login");
      return;
    }
    setCognitoSession(session);
    setEmail(storedEmail);
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (newPassword !== confirm) {
      setError("As senhas não coincidem.");
      return;
    }
    if (newPassword.length < 8) {
      setError("A senha deve ter pelo menos 8 caracteres.");
      return;
    }

    setLoading(true);

    const result = await signIn("cognito-credentials", {
      redirect:       false,
      email,
      password:       "",          // not used in phase 2, but field is required
      cognitoSession,
      newPassword,
    });

    setLoading(false);

    if (result?.error) {
      setError("Não foi possível definir a senha. Verifique os requisitos de complexidade.");
      return;
    }

    // Clean up challenge state and proceed
    sessionStorage.removeItem("cognito_challenge_session");
    sessionStorage.removeItem("cognito_challenge_email");
    router.replace(MAIN_ROUTE);
  };

  if (!cognitoSession) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center",
        justifyContent: "center", background: "#0D0C0B" }}>
        <p style={{ color: "#9A9080", fontSize: 14 }}>A carregar…</p>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center",
      justifyContent: "center", background: "#0D0C0B" }}>
      <div style={{
        background: "#1A1916", border: "1px solid #2E2C28", borderRadius: 12,
        padding: "40px 48px", width: 360, display: "flex", flexDirection: "column", gap: 20,
      }}>
        <div>
          <h1 style={{ color: "#F5F0E8", fontSize: 20, fontWeight: 700, margin: 0 }}>
            Definir nova senha
          </h1>
          <p style={{ color: "#9A9080", fontSize: 13, margin: "8px 0 0" }}>
            Esta é a primeira vez que entras. Define uma senha permanente para{" "}
            <strong style={{ color: "#C8BFB0" }}>{email}</strong>.
          </p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <input
            type="password"
            placeholder="Nova senha (mín. 8 caracteres)"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            autoFocus
            style={inputStyle}
          />
          <input
            type="password"
            placeholder="Confirmar nova senha"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            style={inputStyle}
          />
          {error && <p style={{ color: "#FF6B6B", fontSize: 13, margin: 0 }}>{error}</p>}
          <button
            type="submit"
            disabled={loading}
            style={{
              background: "#3B7A57", color: "#F5F0E8", border: "none", borderRadius: 8,
              padding: "10px 0", fontWeight: 600, cursor: "pointer", fontSize: 15,
              opacity: loading ? 0.6 : 1, marginTop: 4,
            }}
          >
            {loading ? "A guardar…" : "Definir senha e entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
