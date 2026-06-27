import { NextRequest, NextResponse } from "next/server";
import path from "path";
import fs from "fs";
import { getProjectRoot } from "../../../src/lib/data";

// Formatos aceitos — espelha VALID_EXTS do pipeline + outros comuns
const VALID_EXTS = new Set([
  ".mp4", ".avi", ".mov", ".mkv",
  ".webm", ".m4v", ".3gp", ".ts", ".mts", ".m2ts", ".flv", ".wmv",
]);

export const maxDuration = 300; // segundos — necessário para uploads grandes

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const files = formData.getAll("videos") as File[];

    if (!files.length) {
      return NextResponse.json({ error: "Nenhum arquivo recebido." }, { status: 400 });
    }

    const videosDir = path.join(getProjectRoot(), "videos");
    fs.mkdirSync(videosDir, { recursive: true });

    const results: { name: string; ok: boolean; error?: string }[] = [];

    for (const file of files) {
      const ext = path.extname(file.name).toLowerCase();
      if (!VALID_EXTS.has(ext)) {
        results.push({ name: file.name, ok: false, error: `Formato não suportado: ${ext}` });
        continue;
      }

      try {
        const dest = path.join(videosDir, file.name);
        const buf  = Buffer.from(await file.arrayBuffer());
        fs.writeFileSync(dest, buf);
        results.push({ name: file.name, ok: true });
      } catch (e) {
        results.push({ name: file.name, ok: false, error: String(e) });
      }
    }

    const allOk = results.every((r) => r.ok);
    return NextResponse.json({ results }, { status: allOk ? 200 : 207 });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
