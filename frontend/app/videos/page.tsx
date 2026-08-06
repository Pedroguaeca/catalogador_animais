"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { SiabNav } from "../../src/components/SiabNav";
import { VideosPage } from "../../src/components/videos/VideosPage";
import { API_BASE, apiHeaders } from "../../src/lib/api";
import type { VideoItem } from "../../src/lib/videoTypes";

// HOTFIX: ver review/page.tsx — mesmo hardcode do slug antigo, mesma causa
// da tela vazia em produção. Temporário até SIAB-221/222.
const PROJECT_ID = "8ea7e076-3dc9-4fd9-be29-1193dfecceae";

export default function Videos() {
  const { data: session } = useSession();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const idToken = (session as any)?.idToken as string | undefined;

  const [videos,  setVideos]  = useState<VideoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!idToken) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API_BASE}/projects/${PROJECT_ID}/videos`, {
        headers: apiHeaders(idToken),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setVideos(d.videos ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro desconhecido");
    } finally {
      setLoading(false);
    }
  }, [idToken]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="flex flex-col min-h-screen" style={{ background: "#F7F3EE" }}>
      <SiabNav />
      <VideosPage videos={videos} loading={loading} error={error} onRefresh={load} />
    </div>
  );
}
