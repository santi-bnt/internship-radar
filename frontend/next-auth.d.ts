import { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      primaryUserId: string;
    } & DefaultSession["user"];
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    primaryUserId?: string;
    authenticatedEmail?: string;
  }
}
