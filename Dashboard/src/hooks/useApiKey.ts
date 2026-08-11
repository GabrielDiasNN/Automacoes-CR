import { useCallback, useState } from "react";
import { setApiKey as syncClientKey } from "../api/client";

const STORAGE_KEY = "orchestrator_api_key";

export function useApiKey() {
  const [apiKey, setApiKeyState] = useState<string>(
    // sessionStorage: não persiste ao fechar a aba — mais seguro que localStorage (F2)
    () => sessionStorage.getItem(STORAGE_KEY) ?? ""
  );

  const saveKey = useCallback((key: string) => {
    sessionStorage.setItem(STORAGE_KEY, key);
    syncClientKey(key); // sincroniza imediatamente — não depende de useEffect
    setApiKeyState(key);
  }, []);

  const clearKey = useCallback(() => {
    sessionStorage.removeItem(STORAGE_KEY);
    syncClientKey("");
    setApiKeyState("");
  }, []);

  return { apiKey, saveKey, clearKey };
}
