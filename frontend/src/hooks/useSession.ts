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
  uploading: boolean;
  error: string | null;
  addFile: (file: File) => Promise<void>;
  addUrlSource: (url: string) => Promise<void>;
  removeSource: (id: string) => Promise<void>;
  refreshSources: () => void;
}

const POLL_INTERVAL = 2000;

/**
 * Translate an error thrown by any source action into a user-facing string.
 *
 * Covers every structured AppError code the backend may return:
 * - UNSUPPORTED_FILE (415)
 * - FILE_TOO_LARGE   (413)
 * - DUPLICATE_SOURCE (409)
 * - TOO_MANY_SOURCES (400)
 * - UNSAFE_URL       (422)
 * - SOURCE_NOT_FOUND (404)
 * Plus generic network failures (TypeError) and unknown errors.
 */
export function formatSourceActionError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "UNSUPPORTED_FILE":
        return `Unsupported file: ${error.message}`;
      case "FILE_TOO_LARGE":
        return `File too large: ${error.message}`;
      case "DUPLICATE_SOURCE":
        return `Already added: ${error.message}`;
      case "TOO_MANY_SOURCES":
        return `Too many sources: ${error.message}`;
      case "UNSAFE_URL":
        return `Unsafe URL: ${error.message}`;
      default:
        return error.message || fallback;
    }
  }
  if (error instanceof TypeError) return "Network error. Check your connection and try again.";
  return error instanceof Error && error.message ? error.message : fallback;
}

export function useSession(): UseSessionReturn {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sources, setSources] = useState<SourceRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
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
            try {
              const newSid = await createSession();
              sidRef.current = newSid;
              setSessionId(newSid);
              setSources([]);
              setError("Your session expired, please re-add sources.");
            } catch (createError: unknown) {
              setError(formatSourceActionError(createError, "Could not restore your session."));
            }
          } else {
            setError(formatSourceActionError(e, "Could not refresh source status."));
          }
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
      .catch((e: unknown) => setError(formatSourceActionError(e, "Could not start a session.")));
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
      setUploading(true);
      try {
        await uploadFile(sid, file);
        const s = await listSources(sid);
        setSources(s);
        // Resume polling if any source is still processing
        if (s.some((src) => src.status === "processing")) {
          startPolling(sid);
        }
      } catch (e: unknown) {
        setError(formatSourceActionError(e, "Upload failed"));
      } finally {
        setUploading(false);
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
        setError(formatSourceActionError(e, "Failed to add URL"));
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
      setError(formatSourceActionError(e, "Delete failed"));
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
      .catch((e: unknown) => setError(formatSourceActionError(e, "Could not refresh source status.")));
  }, [startPolling]);

  return { sessionId, sources, loading, uploading, error, addFile, addUrlSource, removeSource, refreshSources };
}
