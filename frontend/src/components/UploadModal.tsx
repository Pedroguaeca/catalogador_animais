"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { X, UploadCloud, CheckCircle2, XCircle, Loader2, Play, RotateCcw, HardDrive } from "lucide-react";
import { openDrivePicker, downloadDriveFile } from "../lib/drivePicker";

interface UploadModalProps {
  onClose: () => void;
  onPipelineDone: () => void;
}

const ACCEPT = ".mp4,.avi,.mov,.mkv,.webm,.m4v,.3gp,.ts,.mts,.m2ts,.flv,.wmv";

type FileStatus = "pending" | "uploading" | "done" | "error";

interface VideoFile {
  file: File;
  status: FileStatus;
  progress: number; // 0–100
  error?: string;
}

type PipelineState = "idle" | "running" | "done" | "error";

const EXT_LABEL = "MP4 · AVI · MOV · MKV · WebM · M4V · 3GP · TS · FLV · WMV";

export function UploadModal({ onClose, onPipelineDone }: UploadModalProps) {
  const inputRef       = useRef<HTMLInputElement>(null);
  const dropRef        = useRef<HTMLDivElement>(null);
  const logRef         = useRef<HTMLDivElement>(null);

  const [videos,        setVideos]        = useState<VideoFile[]>([]);
  const [dragging,      setDragging]      = useState(false);
  const [uploading,     setUploading]     = useState(false);
  const [allUploaded,   setAllUploaded]   = useState(false);
  const [pipelineState, setPipelineState] = useState<PipelineState>("idle");
  const [pipelineLog,   setPipelineLog]   = useState<string[]>([]);
  const [driveLoading,  setDriveLoading]  = useState(false);
  const [driveError,    setDriveError]    = useState<string | null>(null);

  // Auto-scroll do log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [pipelineLog]);

  const handleDrivePick = useCallback(async () => {
    setDriveError(null);
    setDriveLoading(true);
    try {
      const picked = await openDrivePicker();
      if (!picked.length) return;

      // Adiciona os arquivos na fila como "uploading" (download em progresso)
      const placeholders: VideoFile[] = picked.map((d) => ({
        file: new File([], d.name, { type: d.mimeType }),
        status: "uploading" as FileStatus,
        progress: 0,
      }));
      setVideos((prev) => {
        const existing = new Set(prev.map((v) => v.file.name));
        return [...prev, ...placeholders.filter((p) => !existing.has(p.file.name))];
      });

      // Baixa cada arquivo do Drive e substitui o placeholder por um File real
      await Promise.all(
        picked.map(async (d) => {
          try {
            const file = await downloadDriveFile(d.id, d.name, d.mimeType, (pct) => {
              setVideos((prev) =>
                prev.map((v) =>
                  v.file.name === d.name ? { ...v, progress: pct } : v
                )
              );
            });
            setVideos((prev) =>
              prev.map((v) =>
                v.file.name === d.name
                  ? { file, status: "pending", progress: 0 }
                  : v
              )
            );
          } catch (err) {
            setVideos((prev) =>
              prev.map((v) =>
                v.file.name === d.name
                  ? { ...v, status: "error", error: String(err) }
                  : v
              )
            );
          }
        })
      );

      setAllUploaded(false);
    } catch (err) {
      setDriveError(String(err));
    } finally {
      setDriveLoading(false);
    }
  }, []);

  const addFiles = useCallback((files: FileList | File[]) => {
    const arr = Array.from(files);
    setVideos((prev) => {
      const existing = new Set(prev.map((v) => v.file.name));
      const fresh = arr
        .filter((f) => !existing.has(f.name))
        .map((f) => ({ file: f, status: "pending" as FileStatus, progress: 0 }));
      return [...prev, ...fresh];
    });
    setAllUploaded(false);
  }, []);

  // Drag & drop
  const onDragOver  = (e: React.DragEvent) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = () => setDragging(false);
  const onDrop      = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  };

  const removeVideo = (name: string) =>
    setVideos((prev) => prev.filter((v) => v.file.name !== name));

  // Upload com XHR para barra de progresso por arquivo
  const uploadOne = (vf: VideoFile): Promise<void> =>
    new Promise((resolve) => {
      const xhr  = new XMLHttpRequest();
      const form = new FormData();
      form.append("videos", vf.file);

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100);
          setVideos((prev) =>
            prev.map((v) => v.file.name === vf.file.name ? { ...v, progress: pct } : v)
          );
        }
      };

      xhr.onload = () => {
        const ok = xhr.status === 200 || xhr.status === 207;
        let errorMsg: string | undefined;
        try {
          const data = JSON.parse(xhr.responseText);
          const res  = data.results?.[0];
          if (res && !res.ok) errorMsg = res.error;
        } catch { /* ignore */ }
        setVideos((prev) =>
          prev.map((v) =>
            v.file.name === vf.file.name
              ? { ...v, status: ok && !errorMsg ? "done" : "error", progress: 100, error: errorMsg }
              : v
          )
        );
        resolve();
      };

      xhr.onerror = () => {
        setVideos((prev) =>
          prev.map((v) =>
            v.file.name === vf.file.name
              ? { ...v, status: "error", error: "Erro de rede" }
              : v
          )
        );
        resolve();
      };

      setVideos((prev) =>
        prev.map((v) => v.file.name === vf.file.name ? { ...v, status: "uploading" } : v)
      );
      xhr.open("POST", "/api/upload");
      xhr.send(form);
    });

  const handleUpload = async () => {
    const pending = videos.filter((v) => v.status === "pending" || v.status === "error");
    if (!pending.length) return;
    setUploading(true);
    // Upload em paralelo (máx 3 simultâneos)
    const chunks: VideoFile[][] = [];
    for (let i = 0; i < pending.length; i += 3) chunks.push(pending.slice(i, i + 3));
    for (const chunk of chunks) await Promise.all(chunk.map(uploadOne));
    setUploading(false);
    setAllUploaded(true);
  };

  const handlePipeline = async () => {
    setPipelineState("running");
    setPipelineLog(["▶ Conectando ao pipeline…"]);

    try {
      const res = await fetch("/api/pipeline", { method: "POST" });
      if (!res.body) throw new Error("Stream vazio");

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   buf     = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") { setPipelineState("done"); continue; }
          try {
            const text = JSON.parse(payload) as string;
            setPipelineLog((l) => [...l, text]);
            if (text.includes("❌")) setPipelineState("error");
          } catch { /* ignore malformed line */ }
        }
      }
    } catch (err) {
      setPipelineLog((l) => [...l, `❌ ${String(err)}`]);
      setPipelineState("error");
    }
  };

  const pendingCount  = videos.filter((v) => v.status === "pending").length;
  const errorCount    = videos.filter((v) => v.status === "error").length;
  const doneCount     = videos.filter((v) => v.status === "done").length;
  const canUpload     = (pendingCount > 0 || errorCount > 0) && !uploading;
  const canPipeline   = allUploaded && doneCount > 0 && pipelineState === "idle";

  const font = { fontFamily: "IBM Plex Sans, sans-serif" };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(34,31,26,0.55)", backdropFilter: "blur(4px)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="flex flex-col"
        style={{
          width: 560,
          maxHeight: "88vh",
          background: "#fff",
          borderRadius: 20,
          boxShadow: "0 8px 60px rgba(34,31,26,0.18)",
          overflow: "hidden",
          ...font,
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: "#EFE8DB" }}>
          <div>
            <p className="font-semibold text-base" style={{ color: "#221F1A", fontFamily: "Libre Franklin, sans-serif" }}>
              Adicionar Vídeos
            </p>
            <p className="text-xs mt-0.5" style={{ color: "#9A9080" }}>{EXT_LABEL}</p>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center rounded-xl transition-colors hover:bg-gray-100"
            style={{ width: 34, height: 34, color: "#9A9080" }}
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-4 min-h-0">
          {/* Drop zone */}
          <div
            ref={dropRef}
            onClick={() => inputRef.current?.click()}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            className="flex flex-col items-center justify-center gap-2 py-8 cursor-pointer transition-colors rounded-2xl"
            style={{
              border: `2px dashed ${dragging ? "#3E8E63" : "#C3BAA8"}`,
              background: dragging ? "#EEF5F0" : "#FAF6EE",
            }}
          >
            <UploadCloud size={32} style={{ color: dragging ? "#2F6B4F" : "#9A9080" }} />
            <p className="text-sm font-medium" style={{ color: "#221F1A" }}>
              Arraste vídeos aqui ou{" "}
              <span style={{ color: "#2F6B4F", textDecoration: "underline" }}>clique para selecionar</span>
            </p>
            <p className="text-xs" style={{ color: "#9A9080" }}>
              Múltiplos arquivos · {EXT_LABEL}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs" style={{ color: "#9A9080" }}>ou</span>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); handleDrivePick(); }}
                disabled={driveLoading}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl transition-colors"
                style={{
                  background: "#fff",
                  border: "1.5px solid #C3BAA8",
                  color: "#221F1A",
                }}
              >
                {driveLoading
                  ? <Loader2 size={12} className="animate-spin" />
                  : <HardDrive size={12} />
                }
                {driveLoading ? "Abrindo Drive…" : "Adicionar do Google Drive"}
              </button>
            </div>
            {driveError && (
              <p className="text-xs mt-1" style={{ color: "#C2503A" }}>{driveError}</p>
            )}
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => e.target.files && addFiles(e.target.files)}
            />
          </div>

          {/* Lista de vídeos */}
          {videos.length > 0 && (
            <div className="flex flex-col gap-2">
              {videos.map((vf) => (
                <div
                  key={vf.file.name}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
                  style={{ background: "#FAF6EE", border: "1px solid #E7DECF" }}
                >
                  {/* Ícone de status */}
                  <span className="shrink-0">
                    {vf.status === "done"      && <CheckCircle2 size={16} style={{ color: "#2F8F4E" }} />}
                    {vf.status === "error"     && <XCircle      size={16} style={{ color: "#C2503A" }} />}
                    {vf.status === "uploading" && <Loader2      size={16} style={{ color: "#2F6B4F" }} className="animate-spin" />}
                    {vf.status === "pending"   && <UploadCloud  size={16} style={{ color: "#9A9080" }} />}
                  </span>

                  {/* Nome + barra */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: "#221F1A" }}>
                      {vf.file.name}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <p className="text-xs" style={{ color: "#9A9080" }}>
                        {(vf.file.size / 1024 / 1024).toFixed(1)} MB
                      </p>
                      {vf.error && (
                        <p className="text-xs" style={{ color: "#C2503A" }}>{vf.error}</p>
                      )}
                    </div>
                    {vf.status === "uploading" && (
                      <div className="mt-1.5 rounded-full overflow-hidden" style={{ height: 3, background: "#EFE8DB" }}>
                        <div
                          className="h-full rounded-full transition-all"
                          style={{ width: `${vf.progress}%`, background: "#3E8E63" }}
                        />
                      </div>
                    )}
                  </div>

                  {/* Remover */}
                  {vf.status !== "uploading" && (
                    <button
                      onClick={() => removeVideo(vf.file.name)}
                      className="shrink-0 rounded-lg transition-colors hover:bg-gray-100 p-1"
                      style={{ color: "#9A9080" }}
                    >
                      <X size={13} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Log do pipeline */}
          {pipelineLog.length > 0 && (
            <div
              ref={logRef}
              className="rounded-xl p-3 overflow-y-auto"
              style={{
                background: "#1A1E1A",
                maxHeight: 200,
                fontFamily: "IBM Plex Mono, monospace",
                fontSize: 11,
                lineHeight: 1.7,
              }}
            >
              {pipelineLog.map((line, i) => (
                <div
                  key={i}
                  style={{
                    color: line.startsWith("✅") ? "#5FD08A"
                         : line.startsWith("❌") ? "#FF6B6B"
                         : line.startsWith("⚠")  ? "#E2A33C"
                         : "#D4D0C8",
                  }}
                >
                  {line}
                </div>
              ))}
              {pipelineState === "running" && (
                <div className="flex items-center gap-2 mt-1" style={{ color: "#9A9080" }}>
                  <Loader2 size={11} className="animate-spin" />
                  processando…
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer com ações */}
        <div className="px-6 py-4 border-t flex items-center justify-between gap-3" style={{ borderColor: "#EFE8DB" }}>
          <p className="text-xs" style={{ color: "#9A9080" }}>
            {videos.length === 0
              ? "Nenhum vídeo adicionado"
              : `${doneCount} enviado${doneCount !== 1 ? "s" : ""} · ${pendingCount} pendente${pendingCount !== 1 ? "s" : ""}`
            }
            {errorCount > 0 && <span style={{ color: "#C2503A" }}> · {errorCount} com erro</span>}
          </p>

          <div className="flex items-center gap-2">
            {/* Re-tentar erros */}
            {errorCount > 0 && !uploading && (
              <button
                onClick={handleUpload}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-xl transition-colors"
                style={{ background: "#FAF6EE", border: "1.5px solid #E7DECF", color: "#6B6357" }}
              >
                <RotateCcw size={12} />
                Re-tentar
              </button>
            )}

            {/* Upload */}
            {canUpload && (
              <button
                onClick={handleUpload}
                disabled={uploading}
                className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white rounded-xl transition-colors"
                style={{ background: "#2F6B4F" }}
                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#3E8E63")}
                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#2F6B4F")}
              >
                {uploading ? <Loader2 size={14} className="animate-spin" /> : <UploadCloud size={14} />}
                {uploading ? "Enviando…" : `Enviar ${pendingCount + errorCount} vídeo${pendingCount + errorCount !== 1 ? "s" : ""}`}
              </button>
            )}

            {/* Processar */}
            {canPipeline && (
              <button
                onClick={handlePipeline}
                className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white rounded-xl transition-colors"
                style={{ background: "#2F6B4F" }}
                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#3E8E63")}
                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#2F6B4F")}
              >
                <Play size={14} />
                Processar vídeos
              </button>
            )}

            {/* Ir para revisão */}
            {pipelineState === "done" && (
              <button
                onClick={() => { onPipelineDone(); onClose(); }}
                className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white rounded-xl"
                style={{ background: "#2F8F4E" }}
              >
                <CheckCircle2 size={14} />
                Ir para revisão
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
