import { NextAuthOptions } from "next-auth";
import CognitoProvider from "next-auth/providers/cognito";

export const authOptions: NextAuthOptions = {
  providers: [
    CognitoProvider({
      clientId:     process.env.COGNITO_CLIENT_ID!,
      clientSecret: process.env.COGNITO_CLIENT_SECRET!,
      issuer:       `https://cognito-idp.us-east-1.amazonaws.com/${process.env.COGNITO_USER_POOL_ID}`,
      checks:       ["pkce", "state", "nonce"],
    }),
  ],
  session: { strategy: "jwt" },
  pages:   { signIn: "/login" },
  callbacks: {
    async jwt({ token, account, profile }) {
      if (account) {
        token.idToken  = account.id_token;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        token.tenantId = (profile as any)?.["custom:tenant_id"] as string | undefined;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        token.role     = (profile as any)?.["custom:role"]      as string | undefined;
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
