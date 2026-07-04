import { NextAuthOptions } from "next-auth";
import CognitoProvider from "next-auth/providers/cognito";
import CredentialsProvider from "next-auth/providers/credentials";
import {
  CognitoIdentityProviderClient,
  InitiateAuthCommand,
  RespondToAuthChallengeCommand,
} from "@aws-sdk/client-cognito-identity-provider";
import { createHmac } from "crypto";

const CLIENT_ID     = process.env.COGNITO_CLIENT_ID!;
const CLIENT_SECRET = process.env.COGNITO_CLIENT_SECRET!;
const REGION        = process.env.COGNITO_REGION ?? "us-east-1";

const cognitoClient = new CognitoIdentityProviderClient({ region: REGION });

function secretHash(username: string): string {
  return createHmac("sha256", CLIENT_SECRET)
    .update(username + CLIENT_ID)
    .digest("base64");
}

// Decode a Cognito id_token without verifying the signature.
// Safe here because the token was just received from Cognito's own endpoint,
// never from untrusted input.
function decodeIdToken(token: string): Record<string, unknown> {
  return JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString("utf-8"));
}

export const authOptions: NextAuthOptions = {
  providers: [
    // ── Google OAuth via Cognito Hosted UI ────────────────────────────────
    CognitoProvider({
      clientId:     CLIENT_ID,
      clientSecret: CLIENT_SECRET,
      issuer:       `https://cognito-idp.us-east-1.amazonaws.com/${process.env.COGNITO_USER_POOL_ID}`,
      checks:       ["pkce", "state", "nonce"],
    }),

    // ── Email + password (USER_PASSWORD_AUTH) ────���────────────────────────
    CredentialsProvider({
      id:   "cognito-credentials",
      name: "Email e senha",
      credentials: {
        email:          { label: "Email",           type: "email" },
        password:       { label: "Senha",           type: "password" },
        // Phase-2 fields — sent only from /definir-senha when responding to challenge
        cognitoSession: { label: "Cognito Session", type: "text" },
        newPassword:    { label: "Nova senha",      type: "password" },
      },
      async authorize(credentials) {
        if (!credentials) return null;
        const { email, password, cognitoSession, newPassword } = credentials;

        // ── Phase 2: user responded to NEW_PASSWORD_REQUIRED ──────────────
        if (cognitoSession && newPassword && email) {
          const res = await cognitoClient.send(new RespondToAuthChallengeCommand({
            ClientId:      CLIENT_ID,
            ChallengeName: "NEW_PASSWORD_REQUIRED",
            Session:       cognitoSession,
            ChallengeResponses: {
              USERNAME:     email,
              NEW_PASSWORD: newPassword,
              SECRET_HASH:  secretHash(email),
            },
          }));
          const auth = res.AuthenticationResult;
          if (!auth?.IdToken) throw new Error("Falha ao definir nova senha.");
          const claims = decodeIdToken(auth.IdToken);
          return {
            id:       claims.sub as string,
            email:    claims.email as string,
            name:     (claims.name ?? claims.email) as string,
            idToken:  auth.IdToken,
            tenantId: claims["custom:tenant_id"] as string | undefined,
            role:     claims["custom:role"]      as string | undefined,
          };
        }

        // ── Phase 1: initial login ──────────────��─────────────────────────
        if (!email || !password) return null;

        let result;
        try {
          result = await cognitoClient.send(new InitiateAuthCommand({
            AuthFlow:       "USER_PASSWORD_AUTH",
            ClientId:       CLIENT_ID,
            AuthParameters: {
              USERNAME:    email,
              PASSWORD:    password,
              SECRET_HASH: secretHash(email),
            },
          }));
        } catch (err: unknown) {
          const code = (err as { name?: string }).name ?? "";
          if (["NotAuthorizedException", "UserNotFoundException", "InvalidParameterException"].includes(code)) {
            // Return null → NextAuth emits "CredentialsSignin" error (no user enumeration)
            return null;
          }
          throw err;
        }

        // NEW_PASSWORD_REQUIRED — encode challenge state and signal the client
        if (result.ChallengeName === "NEW_PASSWORD_REQUIRED") {
          const payload = Buffer.from(
            JSON.stringify({ session: result.Session, email })
          ).toString("base64url");
          throw new Error("NEEDS_NEW_PASSWORD:" + payload);
        }

        const auth = result.AuthenticationResult;
        if (!auth?.IdToken) return null;

        const claims = decodeIdToken(auth.IdToken);
        return {
          id:       claims.sub as string,
          email:    claims.email as string,
          name:     (claims.name ?? claims.email) as string,
          idToken:  auth.IdToken,
          tenantId: claims["custom:tenant_id"] as string | undefined,
          role:     claims["custom:role"]      as string | undefined,
        };
      },
    }),
  ],

  session: { strategy: "jwt" },
  pages:   { signIn: "/login" },

  callbacks: {
    async jwt({ token, account, profile, user }) {
      if (account?.type === "oauth") {
        // Google flow — custom attributes come from the OIDC profile
        token.idToken  = account.id_token;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        token.tenantId = (profile as any)?.["custom:tenant_id"] as string | undefined;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        token.role     = (profile as any)?.["custom:role"]      as string | undefined;
      } else if (account?.type === "credentials" && user) {
        // Credentials flow — authorize() decoded the id_token and attached attributes to user
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        token.idToken  = (user as any).idToken;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        token.tenantId = (user as any).tenantId;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        token.role     = (user as any).role;
      }
      return token;
    },
    async session({ session, token }) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (session as any).idToken  = token.idToken;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (session as any).tenantId = token.tenantId;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (session as any).role     = token.role;
      return session;
    },
  },
};
