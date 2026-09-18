import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./apiClient";
import { mapChaos, mapEarlyGoal, mapMe, mapOpportunity } from "./mappers";

function useAsyncList(loader) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [needsPro, setNeedsPro] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNeedsPro(false);
    try {
      const data = await loader();
      setItems(data);
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) {
        setNeedsPro(true);
        setItems([]);
      } else {
        setError(e.message || "Request failed");
        setItems([]);
      }
    } finally {
      setLoading(false);
    }
  }, [loader]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { items, loading, error, needsPro, reload };
}

export function useMe() {
  const [subscription, setSubscription] = useState({
    entitled: false,
    entitlement: "free",
    status: "free",
    expires_at: null,
    product_id: null,
    prefs: {},
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = mapMe(await api.me());
      setSubscription(data);
    } catch (e) {
      setError(e.message || "Could not load profile");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { subscription, loading, error, reload, setSubscription };
}

export function useOpportunities(limit = 20) {
  const loader = useCallback(async () => {
    const data = await api.opportunities(limit);
    return (data.opportunities || []).map(mapOpportunity);
  }, [limit]);
  return useAsyncList(loader);
}

export function useEarlyGoal(limit = 20) {
  const loader = useCallback(async () => {
    const data = await api.earlyGoal(limit);
    return (data.matches || []).map(mapEarlyGoal);
  }, [limit]);
  return useAsyncList(loader);
}

export function useChaos(limit = 20) {
  const loader = useCallback(async () => {
    const data = await api.chaos(limit);
    return (data.matches || []).map(mapChaos);
  }, [limit]);
  return useAsyncList(loader);
}
