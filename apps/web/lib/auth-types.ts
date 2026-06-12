export interface CurrentUser {
  authenticated: boolean;
  id: string | null;
  email: string | null;
  emailConfirmed: boolean;
  roles: string[];
}

export type AuthStatus = "loading" | "unauthenticated" | "authenticated";
