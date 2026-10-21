import { useCallback, useEffect, useState } from "react";

export function useAsync<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const run = useCallback(() => {
    setLoading(true);
    setError(null);
    fn().then(setData).catch((e: Error) => { setData(null); setError(e.message); }).finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(run, [run]);
  return { data, error, loading, retry: run };
}
