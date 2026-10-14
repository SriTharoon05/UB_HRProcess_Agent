import { createContext, useContext, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, useLocation } from "react-router-dom";
import { api } from "./api";
import type { AuthSession } from "./types";
import { ErrorState, Loading } from "../components/common";

interface AuthValue {
  session: AuthSession | undefined;
  loading: boolean;
  error: Error | null;
  loginDemo: (role: "candidate" | "hr") => Promise<void>;
  loginHR: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => void;
}
const AuthContext = createContext<AuthValue | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["session"],
    queryFn: api.session,
    staleTime: 60_000,
    retry: false,
  });
  async function loginDemo(role: "candidate" | "hr") {
    const session = await api.demoLogin(role);
    await client.cancelQueries();
    client.removeQueries({
      predicate: (item) => item.queryKey[0] !== "session",
    });
    client.setQueryData(["session"], session);
  }
  async function loginHR(username: string, password: string) {
    const session = await api.hrLogin(username, password);
    await client.cancelQueries();
    client.removeQueries({
      predicate: (item) => item.queryKey[0] !== "session",
    });
    client.setQueryData(["session"], session);
  }
  async function logout() {
    await api.logout();
    await client.cancelQueries();
    client.removeQueries({
      predicate: (item) => item.queryKey[0] !== "session",
    });
    const session = await api.session();
    client.setQueryData(["session"], session);
  }
  return (
    <AuthContext.Provider
      value={{
        session: query.data,
        loading: query.isPending,
        error: query.error,
        loginDemo,
        loginHR,
        logout,
        refresh: () => {
          void query.refetch();
        },
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
// This hook lives beside its provider so authentication has a single shared state.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider is required");
  return value;
}
export function Protected({
  role,
  children,
}: {
  role: "candidate" | "hr";
  children: ReactNode;
}) {
  const { session, loading, error, refresh } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} retry={refresh} />;
  if (!session?.user || session.user.role !== role)
    return (
      <Navigate
        to={role === "hr" ? "/hr/login" : "/login"}
        state={{ from: `${location.pathname}${location.search}${location.hash}` }}
        replace
      />
    );
  return <>{children}</>;
}
