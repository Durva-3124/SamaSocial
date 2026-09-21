import { useCallback, useEffect, useRef, useState } from "react";
import {
  addUrl,
  createSession,
  deleteSource,
  listSources,
  uploadFile,
  type SourceRecord,
} from "../api/sessions";

export interface UseSessionReturn {
  sessionId: string | null;
  sources: SourceRecord[];
  loading: boolean;
  error: string | null;
  addFile: (file: File) => Promise<void>;
  addUrlSource: (url: string) => Promise<void>;
  removeSource: (id: string) => Promise<void>;
  refreshSources: () => void;
}

const POLL_INTERVAL = 2000;

export function useSession(): UseSessionReturn {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sources, setSources] = useState<SourceRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchSources = useCallback(async (sid: string) => {
    try {
      const s = await listSources(sid);
      setSources(s);
    } catch {
      // silent — polling will retry
    }
  }, []);

  const startPolling = useCallback(
    (sid: string) => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(() => fetchSources(sid), POLL_INTERVAL);
    },
    [fetchSources],
  );

  useEffect(() => {
    let cancelled = false;
    createSession()
      .then((sid) => {
        if (cancelled) return;
        setSessionId(sid);
        startPolling(sid);
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [startPolling]);

  const addFile = useCallback(
    async (file: File) => {
      if (!sessionId) return;
      setLoading(true);
      setError(null);
      try {
        await uploadFile(sessionId, file);
        await fetchSources(sessionId);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Upload failed");
      } finally {
        setLoading(false);
      }
    },
    [sessionId, fetchSources],
  );

  const addUrlSource = useCallback(
    async (url: string) => {
      if (!sessionId) return;
      setLoading(true);
      setError(null);
      try {
        await addUrl(sessionId, url);
        await fetchSources(sessionId);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to add URL");
      } finally {
        setLoading(false);
      }
    },
    [sessionId, fetchSources],
  );

  const removeSource = useCallback(
    async (id: string) => {
      if (!sessionId) return;
      try {
        await deleteSource(sessionId, id);
        setSources((prev) => prev.filter((s) => s.id !== id));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Delete failed");
      }
    },
    [sessionId],
  );

  const refreshSources = useCallback(() => {
    if (sessionId) fetchSources(sessionId);
  }, [sessionId, fetchSources]);

  return { sessionId, sources, loading, error, addFile, addUrlSource, removeSource, refreshSources };
}
