"use client";

import { useState } from "react";
import { HardDrive, Loader2 } from "lucide-react";
import { openDrivePicker, downloadDriveFile } from "../lib/drivePicker";

interface GoogleDriveButtonProps {
  // Chamado com os File reais já baixados do Drive — o chamador decide o
  // destino (SIAB-176: entra na mesma fila/fluxo real de upload do
  // drag-and-drop local, addFiles() em app/upload/page.tsx, não duplica
  // lógica de upload aqui).
  onFilesReady: (files: File[]) => void;
  disabled?: boolean;
}

// SIAB-176: só a parte "trazer arquivo do Drive pro navegador" — OAuth +
// Picker API + download, lógica que já existia em UploadModal.tsx (agora
// removido, era um componente órfão nunca importado em lugar nenhum, e
// subia pra /api/upload local — pipeline antigo, incompatível com Vercel
// serverless). O destino do arquivo baixado não é mais problema deste
// componente.
export function GoogleDriveButton({ onFilesReady, disabled }: GoogleDriveButtonProps) {
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [progress, setProgress] = useState<Record<string, number>>({});

  const handleClick = async () => {
    setError(null);
    setLoading(true);
    setProgress({});
    try {
      const picked = await openDrivePicker();
      if (!picked.length) return; // usuário cancelou o picker

      const results = await Promise.allSettled(
        picked.map((d) =>
          downloadDriveFile(d.id, d.name, d.mimeType, (pct) =>
            setProgress((prev) => ({ ...prev, [d.name]: pct }))
          )
        )
      );

      const files  = results
        .filter((r): r is PromiseFulfilledResult<File> => r.status === "fulfilled")
        .map((r) => r.value);
      const failed = results.filter((r) => r.status === "rejected").length;

      if (files.length) onFilesReady(files);
      if (failed) {
        setError(
          `${failed} de ${picked.length} arquivo${picked.length !== 1 ? "s" : ""} não pôde ser baixado do Drive.`
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
      setProgress({});
    }
  };

  return (
    <div className="flex flex-col items-center gap-1.5">
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); handleClick(); }}
        disabled={disabled || loading}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl transition-colors"
        style={{ background: "#fff", border: "1.5px solid #C3BAA8", color: "#221F1A" }}
      >
        {loading ? <Loader2 size={12} className="animate-spin" /> : <HardDrive size={12} />}
        {loading ? "Baixando do Drive…" : "Adicionar do Google Drive"}
      </button>

      {loading && Object.keys(progress).length > 0 && (
        <div className="flex flex-col gap-0.5 items-center">
          {Object.entries(progress).map(([name, pct]) => (
            <span key={name} className="text-xs" style={{ color: "#9A9080" }}>
              {name} — {pct}%
            </span>
          ))}
        </div>
      )}

      {error && (
        <p className="text-xs" style={{ color: "#C2503A" }}>{error}</p>
      )}
    </div>
  );
}
