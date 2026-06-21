import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useApiKey } from "../hooks/useApiKey";
import { setApiKey } from "../api/client";

interface ApiKeyContextValue {
  apiKey: string;
  saveKey: (key: string) => void;
  clearKey: () => void;
  hasKey: boolean;
}

const ApiKeyContext = createContext<ApiKeyContextValue | null>(null);

export function ApiKeyProvider({ children }: { children: ReactNode }) {
  const { apiKey, saveKey, clearKey } = useApiKey();

  // Sincroniza o cliente de API sempre que a key mudar
  useEffect(() => {
    setApiKey(apiKey);
  }, [apiKey]);

  return (
    <ApiKeyContext.Provider value={{ apiKey, saveKey, clearKey, hasKey: !!apiKey }}>
      {children}
    </ApiKeyContext.Provider>
  );
}

export function useApiKeyContext() {
  const ctx = useContext(ApiKeyContext);
  if (!ctx) throw new Error("useApiKeyContext deve ser usado dentro de ApiKeyProvider");
  return ctx;
}
