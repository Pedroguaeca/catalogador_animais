"use client";

import { useCallback, useRef, useState } from "react";
import {
  UploadCloud, CheckCircle2, XCircle, Loader2, Camera, Clock, MapPin, X,
} from "lucide-react";
import { SiabNav } from "../../src/components/SiabNav";

const PROJECTS = ["projeto-junho-2026"];
const ACCEPT   = ".avi,.mp4,.mov,.mkv";

interface UploadResult {
  video_id:        string;
  s3_key:          string;
  camera_id:       string | null;
  captured_at:     string | null;
  location_source: string;
}

interface FileItem {
  id:       string;
  file:     File;
  status:   "pending" | "uploading" | "done" | "error";
  progress: number;
  result:   UploadResult | null;
  error:    string | null;
}

const SOURCE_LABEL: Record<string, string> = {
  metadata: "Metadados do arquivo",
  ocr:      "OCR no overlay",
  manual:   "Preenchimento manual necessário",
};

function mkId() {
  return Math.random().toString(36).slice(2);
}

function toItems(files: File[]): FileItem[] {
  return files.map((file) => ({
    id: mkId(), file, status: "pending", progress: 0, result: null, error: null,
  }));
}

export default function UploadPage() {
  const inputRef = useRef<HTMLInputElement>(null);

  const [project,  setProject]  = useState(PROJECTS[0]);
  const [items,    setItems]    = useState<FileItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [running,  setRunning]  = useState(false);

  const addFiles = useCallback((files: File[]) => {
    if (!files.length) return;
    setItems((prev) => {
      const existing = new Set(prev.map((i) => i.file.name));
      const novel    = files.filter((f) => !existing.has(f.name));
      return [...prev, ...toItems(novel)];
    });
  }, []);

  const removeItem = (id: string) =>
    setItems((prev) => prev.filter((i) => i.id !== id));

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    addFiles(Array.from(e.dataTransfer.files));
  };

  const patch = (id: string, update: Partial<FileItem>) =>
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, ...update } : i)));

  const uploadOne = (item: FileItem): Promise<void> =>
    new Promise((resolve) => {
      patch(item.id, { status: "uploading", progress: 0 });

      const form = new FormData();
      form.append("file", item.file);

      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable)
          patch(item.id, { progress: Math.round((e.loaded / e.total) * 100) });
      };
      xhr.onload = () => {
        if (xhr.status === 200) {
          patch(item.id, { status: "done", progress: 100, result: JSON.parse(xhr.responseText) });
        } else {
          patch(item.id, { status: "error", error: `Erro ${xhr.status}: ${xhr.responseText}` });
        }
        resolve();
      };
      xhr.onerror = () => {
        patch(item.id, { status: "error", error: "Erro de rede — verifique se a API está rodando em :8000." });
        resolve();
      };
      xhr.open("POST", `/api/v1/projects/${project}/videos/upload`);
      xhr.send(form);
    });

  const handleSubmit = async () => {
    const pending = items.filter((i) => i.status === "pending");
    if (!pending.length) return;
    setRunning(true);
    for (const item of pending) {
      await uploadOne(item);
    }
    setRunning(false);
  };

  const pendingCount  = items.filter((i) => i.status === "pending").length;
  const canSubmit     = pendingCount > 0 && !running;

  const F = { fontFamily: "IBM Plex Sans, sans-serif" };

  return (
    <div className="min-h-screen" style={{ background: "#FAF6EE", ...F }}>
      <SiabNav />

      <main className="max-w-xl mx-auto px-4 py-10 flex flex-col gap-6">
        {/* Cabeçalho */}
        <div>
          <h1 className="text-xl font-semibold font-title" style={{ color: "#221F1A" }}>
            Upload de Vídeos
          </h1>
          <p className="text-sm mt-1" style={{ color: "#9A9080" }}>
            O sistema extrai automaticamente câmera e timestamp do overlay.
          </p>
        </div>

        {/* Card principal */}
        <div
          className="flex flex-col gap-5 p-6 rounded-2xl bg-white"
          style={{ border: "1px solid #E7DECF", boxShadow: "0 1px 2px rgba(34,31,26,.04), 0 6px 20px rgba(34,31,26,.05)" }}
        >
          {/* Projeto */}
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium" style={{ color: "#6B6357" }}>Projeto</span>
            <select
              value={project}
              onChange={(e) => setProject(e.target.value)}
              style={{
                padding: "8px 12px", borderRadius: 10, fontSize: 13,
                border: "1.5px solid #E7DECF", background: "#FAF6EE",
                color: "#221F1A", fontFamily: "IBM Plex Sans, sans-serif",
              }}
            >
              {PROJECTS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>

          {/* Drop zone */}
          <div
            onClick={() => !running && inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className="flex flex-col items-center justify-center gap-2.5 py-8 rounded-2xl cursor-pointer"
            style={{
              border: `2px dashed ${dragging ? "#3E8E63" : items.length ? "#CDE3D6" : "#C3BAA8"}`,
              background: dragging ? "#EEF5F0" : items.length ? "#F4FBF6" : "#FAF6EE",
              transition: "all 0.15s",
            }}
          >
            <UploadCloud size={30} style={{ color: items.length ? "#2F8F4E" : dragging ? "#2F6B4F" : "#9A9080" }} />
            {items.length ? (
              <>
                <p className="text-sm font-medium" style={{ color: "#2F8F4E" }}>
                  {items.length} arquivo{items.length !== 1 ? "s" : ""} na fila
                </p>
                <p className="text-xs" style={{ color: "#9A9080" }}>arraste mais ou clique para adicionar</p>
              </>
            ) : (
              <>
                <p className="text-sm font-medium" style={{ color: "#221F1A" }}>
                  Arraste vídeos ou{" "}
                  <span style={{ color: "#2F6B4F", textDecoration: "underline" }}>clique para selecionar</span>
                </p>
                <p className="text-xs" style={{ color: "#9A9080" }}>AVI · MP4 · MOV · MKV · múltiplos arquivos aceitos</p>
              </>
            )}
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              multiple
              className="hidden"
              onChange={(e) => {
                if (e.target.files) addFiles(Array.from(e.target.files));
                e.target.value = "";
              }}
            />
          </div>

          {/* Botão enviar */}
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white transition-colors"
            style={{
              background: !canSubmit ? "#C3BAA8" : "#2F6B4F",
              cursor:     !canSubmit ? "not-allowed" : "pointer",
            }}
            onMouseEnter={(e) => { if (canSubmit) (e.currentTarget as HTMLElement).style.background = "#3E8E63"; }}
            onMouseLeave={(e) => { if (canSubmit) (e.currentTarget as HTMLElement).style.background = "#2F6B4F"; }}
          >
            {running
              ? <><Loader2 size={15} className="animate-spin" /> Processando…</>
              : <><UploadCloud size={15} /> Enviar {pendingCount > 1 ? `${pendingCount} vídeos` : "vídeo"}</>
            }
          </button>
        </div>

        {/* Lista de arquivos */}
        {items.length > 0 && (
          <div className="flex flex-col gap-3">
            {items.map((item) => (
              <FileCard key={item.id} item={item} onRemove={() => removeItem(item.id)} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function FileCard({ item, onRemove }: { item: FileItem; onRemove: () => void }) {
  const F = { fontFamily: "IBM Plex Sans, sans-serif" };

  const borderColor =
    item.status === "done"     ? "#CDE3D6" :
    item.status === "error"    ? "#F5C7BB" :
    item.status === "uploading" ? "#D4E5FF" :
    "#E7DECF";

  const bg =
    item.status === "done"     ? "#EEF5F0" :
    item.status === "error"    ? "#FEF2EF" :
    item.status === "uploading" ? "#F2F7FF" :
    "#FFFFFF";

  return (
    <div
      className="flex flex-col gap-3 p-4 rounded-2xl"
      style={{ background: bg, border: `1.5px solid ${borderColor}`, ...F }}
    >
      {/* Linha do nome */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          {item.status === "uploading" && <Loader2 size={14} className="animate-spin flex-shrink-0" style={{ color: "#4A90D9" }} />}
          {item.status === "done"      && <CheckCircle2 size={14} className="flex-shrink-0" style={{ color: "#2F8F4E" }} />}
          {item.status === "error"     && <XCircle size={14} className="flex-shrink-0" style={{ color: "#C2503A" }} />}
          {item.status === "pending"   && <div style={{ width: 14, height: 14, borderRadius: "50%", border: "2px solid #C3BAA8", flexShrink: 0 }} />}
          <span
            className="text-sm font-medium truncate"
            style={{ color: item.status === "error" ? "#C2503A" : "#221F1A" }}
          >
            {item.file.name}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-xs" style={{ color: "#9A9080" }}>
            {(item.file.size / 1024 / 1024).toFixed(1)} MB
          </span>
          {item.status === "pending" && (
            <button
              onClick={onRemove}
              style={{ padding: 2, background: "none", border: "none", cursor: "pointer", color: "#9A9080" }}
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Barra de progresso durante upload */}
      {item.status === "uploading" && (
        <div className="flex flex-col gap-1">
          <div className="flex justify-between text-xs" style={{ color: "#6B8FB5" }}>
            <span>Enviando…</span>
            <span>{item.progress}%</span>
          </div>
          <div className="rounded-full overflow-hidden" style={{ height: 3, background: "#D4E5FF" }}>
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{ width: `${item.progress}%`, background: "#4A90D9" }}
            />
          </div>
        </div>
      )}

      {/* Resultado */}
      {item.status === "done" && item.result && (
        <>
          <div className="grid grid-cols-2 gap-2.5">
            <InfoRow icon={<Camera size={12} />} label="Câmera"    value={item.result.camera_id   ?? "—"} />
            <InfoRow icon={<Clock size={12} />}  label="Timestamp" value={item.result.captured_at ?? "—"} />
            <InfoRow icon={<MapPin size={12} />} label="Origem"    value={SOURCE_LABEL[item.result.location_source] ?? item.result.location_source} />
            <InfoRow icon={null}                 label="Video ID"  value={item.result.video_id.slice(0, 8) + "…"} mono />
          </div>
          {item.result.location_source === "manual" && (
            <p className="text-xs" style={{ color: "#E2A33C" }}>
              Timestamp e câmera não encontrados automaticamente — preencha na revisão.
            </p>
          )}
        </>
      )}

      {/* Erro */}
      {item.status === "error" && item.error && (
        <p className="text-xs" style={{ color: "#C2503A" }}>{item.error}</p>
      )}
    </div>
  );
}

function InfoRow({
  icon, label, value, mono = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-1.5" style={{ color: "#6B6357" }}>
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <span
        className="text-sm font-medium"
        style={{
          color: "#221F1A",
          fontFamily: mono ? "IBM Plex Mono, monospace" : "IBM Plex Sans, sans-serif",
        }}
      >
        {value}
      </span>
    </div>
  );
}
