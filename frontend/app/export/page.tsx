"use client";

import { useEffect, useState } from "react";
import { Download, CheckCircle2, Loader2, AlertCircle } from "lucide-react";
import { useSession } from "next-auth/react";
import { SiabNav } from "../../src/components/SiabNav";
import { ProjectSelector } from "../../src/components/ProjectSelector";
import { API_BASE, apiHeaders } from "../../src/lib/api";
import { useProjectsAndClients } from "../../src/lib/projectTypes";

type ExportState = "idle" | "loading" | "done" | "error";

export default function ExportPage() {
  const { data: session } = useSession();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const idToken = (session as any)?.idToken as string | undefined;

  const { projects, clients, loading: loadingProjects, error: projectsError } = useProjectsAndClients(idToken);
  const [project, setProject] = useState("");

  // Mesmo comportamento de antes (sempre um projeto pré-selecionado) — só
  // que agora vindo da lista real em vez de fixo.
  useEffect(() => {
    if (!project && projects.length > 0) setProject(projects[0].project_id);
  }, [projects, project]);

  const [exportState, setExportState] = useState<ExportState>("idle");
  const [error,       setError]       = useState<string | null>(null);
  const [filename,    setFilename]    = useState<string | null>(null);

  const handleExport = async () => {
    setExportState("loading");
    setError(null);
    setFilename(null);

    try {
      const res = await fetch(`${API_BASE}/projects/${project}/appearances/export`, { headers: apiHeaders(idToken) });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);

      // Extrai nome do arquivo do header Content-Disposition
      const cd   = res.headers.get("content-disposition") ?? "";
      const name = cd.match(/filename="([^"]+)"/)?.[1]
        ?? `siab_${project}_${new Date().toISOString().slice(0, 10)}.csv`;

      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = name;
      // Precisa estar no DOM antes do .click() — alguns navegadores (Safari)
      // ignoram silenciosamente o clique num <a> desanexado.
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      setFilename(name);
      setExportState("done");
    } catch (e) {
      setError(String(e));
      setExportState("error");
    }
  };

  const F = { fontFamily: "IBM Plex Sans, sans-serif" };

  return (
    <div className="min-h-screen" style={{ background: "#FAF6EE", ...F }}>
      <SiabNav />

      <main className="max-w-md mx-auto px-4 py-10 flex flex-col gap-6">
        {/* Header */}
        <div>
          <h1 className="text-xl font-semibold font-title" style={{ color: "#221F1A" }}>
            Exportar CSV
          </h1>
          <p className="text-sm mt-1" style={{ color: "#9A9080" }}>
            Exporta todas as aparições confirmadas no formato do formulário de campo.
          </p>
        </div>

        {/* Card */}
        <div
          className="flex flex-col gap-5 p-6 rounded-2xl bg-white"
          style={{ border: "1px solid #E7DECF", boxShadow: "0 1px 2px rgba(34,31,26,.04), 0 6px 20px rgba(34,31,26,.05)" }}
        >
          {/* Projeto */}
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium" style={{ color: "#6B6357" }}>Projeto</span>
            <ProjectSelector
              projects={projects}
              clients={clients}
              value={project}
              onChange={(id) => { setProject(id); setExportState("idle"); }}
              disabled={loadingProjects && projects.length === 0}
            />
            {projectsError && (
              <span className="text-xs" style={{ color: "#C2503A" }}>{projectsError}</span>
            )}
          </label>

          {/* Colunas do CSV */}
          <div className="rounded-xl p-3" style={{ background: "#FAF6EE", border: "1px solid #E7DECF" }}>
            <p className="text-xs font-medium mb-2" style={{ color: "#6B6357" }}>Colunas exportadas</p>
            <div className="flex flex-wrap gap-1.5">
              {[
                "nome_arquivo", "camera", "lat", "long",
                "data", "horario", "periodo",
                "nome_popular", "nome_cientifico", "nivel_taxonomico", "grupo_fauna",
                "n_individuos", "qualidade", "obs",
              ].map((col) => (
                <span
                  key={col}
                  className="px-2 py-0.5 rounded-full text-xs"
                  style={{
                    background: "#EFE8DB", color: "#6B6357",
                    fontFamily: "IBM Plex Mono, monospace",
                  }}
                >
                  {col}
                </span>
              ))}
            </div>
          </div>

          {/* Botão */}
          <button
            onClick={handleExport}
            disabled={exportState === "loading"}
            className="flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white transition-colors"
            style={{
              background: exportState === "loading" ? "#C3BAA8" : "#2F6B4F",
              cursor: exportState === "loading" ? "not-allowed" : "pointer",
            }}
            onMouseEnter={(e) => { if (exportState !== "loading") (e.currentTarget as HTMLElement).style.background = "#3E8E63"; }}
            onMouseLeave={(e) => { if (exportState !== "loading") (e.currentTarget as HTMLElement).style.background = "#2F6B4F"; }}
          >
            {exportState === "loading"
              ? <><Loader2 size={15} className="animate-spin" /> Gerando CSV…</>
              : <><Download size={15} /> Exportar CSV</>
            }
          </button>
        </div>

        {/* Sucesso */}
        {exportState === "done" && filename && (
          <div
            className="flex items-center gap-3 p-4 rounded-xl"
            style={{ background: "#EEF5F0", border: "1.5px solid #CDE3D6" }}
          >
            <CheckCircle2 size={16} style={{ color: "#2F8F4E", flexShrink: 0 }} />
            <div>
              <p className="text-sm font-medium" style={{ color: "#2F6B4F" }}>Download iniciado</p>
              <p className="text-xs mt-0.5" style={{ color: "#6B6357", fontFamily: "IBM Plex Mono, monospace" }}>
                {filename}
              </p>
            </div>
          </div>
        )}

        {/* Erro */}
        {exportState === "error" && error && (
          <div
            className="flex items-start gap-3 p-4 rounded-xl"
            style={{ background: "#FEF2EF", border: "1.5px solid #F5C7BB" }}
          >
            <AlertCircle size={16} style={{ color: "#C2503A", flexShrink: 0, marginTop: 1 }} />
            <div>
              <p className="text-sm font-medium" style={{ color: "#C2503A" }}>Falha na exportação</p>
              <p className="text-xs mt-0.5" style={{ color: "#C2503A" }}>{error}</p>
              <p className="text-xs mt-1" style={{ color: "#9A9080" }}>
                Verifique se a API está rodando em localhost:8000
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
