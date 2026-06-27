import { NextResponse } from "next/server";
import { spawn } from "child_process";
import { getProjectRoot } from "../../../src/lib/data";

export const maxDuration = 600;

export async function POST() {
  // ── Modo Docker: proxy para o container pipeline ──────────────────────────
  const pipelineUrl = process.env.PIPELINE_URL;
  if (pipelineUrl) {
    const upstream = await fetch(`${pipelineUrl}/run`, { method: "POST" });
    return new NextResponse(upstream.body, {
      headers: {
        "Content-Type":  "text/event-stream",
        "Cache-Control": "no-cache",
        Connection:      "keep-alive",
      },
    });
  }

  // ── Modo dev local: spawn conda run ───────────────────────────────────────
  const projectRoot = getProjectRoot();
  const encoder     = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      const send = (line: string) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(line)}\n\n`));
      };

      send("▶ Iniciando pipeline…");
      send(`📁 Projeto: ${projectRoot}`);

      const proc = spawn(
        "/opt/anaconda3/bin/conda",
        ["run", "-n", "catalogo", "--no-capture-output", "python", "main.py"],
        { cwd: projectRoot, env: { ...process.env, PYTHONUNBUFFERED: "1" } }
      );

      proc.stdout.on("data", (data: Buffer) => {
        data.toString().split("\n").filter(Boolean).forEach(send);
      });
      proc.stderr.on("data", (data: Buffer) => {
        data.toString().split("\n").filter(Boolean).forEach((l) => send(`⚠ ${l}`));
      });
      proc.on("error", (err) => {
        send(`❌ Erro ao iniciar processo: ${err.message}`);
        controller.close();
      });
      proc.on("close", (code) => {
        send(code === 0 ? "✅ Pipeline concluído!" : `❌ Código de saída: ${code}`);
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        controller.close();
      });
    },
  });

  return new NextResponse(stream, {
    headers: {
      "Content-Type":  "text/event-stream",
      "Cache-Control": "no-cache",
      Connection:      "keep-alive",
    },
  });
}
