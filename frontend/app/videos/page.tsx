"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { SiabNav } from "../../src/components/SiabNav";
import { VideosPage } from "../../src/components/videos/VideosPage";
import { API_BASE, apiHeaders } from "../../src/lib/api";
import { useProjectsAndClients } from "../../src/lib/projectTypes";
import type { VideoItem } from "../../src/lib/videoTypes";

export default function Videos() {
  const { data: session } = useSession();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const idToken = (session as any)?.idToken as string | undefined;

  const { projects, clients, loading: loadingProjects, error: projectsError } = useProjectsAndClients(idToken);
  const [projectId, setProjectId] = useState("");

  useEffect(() => {
    if (!projectId && projects.length > 0) setProjectId(projects[0].project_id);
  }, [projects, projectId]);

  const [videos,  setVideos]  = useState<VideoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!idToken || !projectId) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API_BASE}/projects/${projectId}/videos`, {
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
  }, [idToken, projectId]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="flex flex-col min-h-screen" style={{ background: "#F7F3EE" }}>
      <SiabNav />
      <VideosPage
        videos={videos}
        loading={loading || loadingProjects}
        error={error ?? projectsError}
        onRefresh={load}
        projects={projects}
        clients={clients}
        projectId={projectId}
        onProjectChange={setProjectId}
      />
    </div>
  );
}
