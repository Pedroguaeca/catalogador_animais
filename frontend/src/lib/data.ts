// Leitura server-side dos dados do pipeline (CSV + genus_map.json).
// Usado diretamente por server components — sem fetch HTTP circular.

import path from "path";
import fs from "fs";
import { parse } from "csv-parse/sync";
import type { Video } from "./types";

// Em Docker, DATA_ROOT aponta para o volume compartilhado (/data).
// Em dev local, sobe um nível a partir de frontend/.
const PROJECT_ROOT = process.env.DATA_ROOT ?? path.resolve(process.cwd(), "..");

export function getProjectRoot(): string {
  return PROJECT_ROOT;
}

export function getFramesRoot(): string {
  return path.join(PROJECT_ROOT, "frames");
}

function loadGenusMap(): Record<string, { pt: string; en: string }> {
  const p = path.join(PROJECT_ROOT, "genus_map.json");
  if (!fs.existsSync(p)) return {};
  const raw = JSON.parse(fs.readFileSync(p, "utf-8"));
  return Object.fromEntries(
    Object.entries(raw).filter(([k]) => !k.startsWith("_"))
  ) as Record<string, { pt: string; en: string }>;
}

export function loadVideos(): Video[] {
  const csvPath = path.join(PROJECT_ROOT, "resultados", "catalogo_animais.csv");
  if (!fs.existsSync(csvPath)) return [];

  const genusMap = loadGenusMap();
  const raw = fs.readFileSync(csvPath, "utf-8");
  const rows: Record<string, string>[] = parse(raw, {
    columns: true,
    skip_empty_lines: true,
  });

  // Agrupa por vídeo; para cada vídeo, acumula frames únicos (pelo path)
  const byVideo: Record<string, Map<string, Record<string, string>>> = {};
  for (const row of rows) {
    const vid = row["video"] ?? "unknown";
    if (!byVideo[vid]) byVideo[vid] = new Map();
    const fp = row["frame"] ?? "";
    if (fp && !byVideo[vid].has(fp)) {
      byVideo[vid].set(fp, row);
    }
  }

  return Object.entries(byVideo).map(([videoId, frameMap]) => {
    const frames = Array.from(frameMap.entries()).map(([framePath, row], i) => {
      const genus    = row["genero"]   ?? "Unknown";
      const genusPt  = genusMap[genus]?.pt ?? row["genero_pt"] ?? genus;
      const detConf  = parseFloat(row["det_conf"] ?? "0");
      const clsConf  = parseFloat(row["cls_conf"]  ?? "0");
      const x1 = parseFloat(row["x1"] ?? "0");
      const y1 = parseFloat(row["y1"] ?? "0");
      const x2 = parseFloat(row["x2"] ?? "0");
      const y2 = parseFloat(row["y2"] ?? "0");
      const date = row["data"] ?? "";
      const time = row["hora"] ?? "";
      const dateFmt = date ? date.split("-").reverse().join("-") : "";

      const video_uuid = framePath.split("/")[0] ?? "";

      return {
        idx: i + 1,
        path: framePath,          // relativo à pasta frames/
        video_uuid,               // primeiro segmento = UUID usado nas S3 keys
        timestamp: dateFmt && time ? `${dateFmt} · ${time}` : "",
        date,
        time,
        detection:
          clsConf > 0
            ? { genus, genus_pt: genusPt, det_conf: detConf, cls_conf: clsConf,
                bbox: [x1, y1, x2, y2] as [number, number, number, number] }
            : null,
        status: (clsConf >= 0.3 ? "detection" : clsConf > 0 ? "review" : "empty") as
          "detection" | "review" | "empty",
      };
    });

    return { id: videoId, frames };
  });
}
