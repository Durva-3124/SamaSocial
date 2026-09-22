import { useCallback, useEffect, useRef, useState } from "react";
import {
  addUrl,
  createSession,
  deleteSource,
  listSources,
  uploadFile,
  type SourceRecord,
} from "../api/sessions";
import { ApiError } from "../api/client";

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
  const sidRef = useRef<string | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (sid: string) => {
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const s = await listSources(sid);
          setSources(s);
          if (s.length > 0 && s.every((src) => src.status !== "processing")) {
            stopPolling();
          }
        } catch (e: unknown) {
          if (e instanceof ApiError && e.status === 404) {
            stopPolling();
            // Session expired — create a new one and notify the user
            const newSid = await createSession();
            sidRef.current = newSid;
            setSessionId(newSid);
            setSources([]);
            setError("Your session expired, please re-add sources.");
          }
          // other errors: silent, polling will retry
        }
      }, POLL_INTERVAL);
    },
    [stopPolling],
  );

  // Bootstrap: create initial session
  useEffect(() => {
    let cancelled = false;
    createSession()
      .then((sid) => {
        if (cancelled) return;
        sidRef.current = sid;
        setSessionId(sid);
        // Don't start polling until there's something to poll
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [stopPolling]);

  const addFile = useCallback(
    async (file: File) => {
      const sid = sidRef.current;
      if (!sid) return;
      setLoading(true);
      setError(null);
      try {
        await uploadFile(sid, file);
        const s = await listSources(sid);
        setSources(s);
        // Resume polling if any source is still processing
        if (s.some((src) => src.status === "processing")) {
          startPolling(sid);
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Upload failed");
      } finally {
        setLoading(false);
      }
    },
    [startPolling],
  );

  const addUrlSource = useCallback(
    async (url: string) => {
      const sid = sidRef.current;
      if (!sid) return;
      setLoading(true);
      setError(null);
      try {
        await addUrl(sid, url);
        const s = await listSources(sid);
        setSources(s);
        if (s.some((src) => src.status === "processing")) {
          startPolling(sid);
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to add URL");
      } finally {
        setLoading(false);
      }
    },
    [startPolling],
  );

  const removeSource = useCallback(async (id: string) => {
    const sid = sidRef.current;
    if (!sid) return;
    try {
      await deleteSource(sid, id);
      setSources((prev) => prev.filter((s) => s.id !== id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }, []);

  const refreshSources = useCallback(() => {
    const sid = sidRef.current;
    if (!sid) return;
    listSources(sid)
      .then((s) => {
        setSources(s);
        if (s.some((src) => src.status === "processing")) startPolling(sid);
      })
      .catch(() => {/* silent */});
  }, [startPolling]);

  return { sessionId, sources, loading, error, addFile, addUrlSource, removeSource, refreshSources };
}
