"use client";

import { useRef, useEffect, useCallback } from "react";
import { Maximize2, ZoomIn, Check } from "lucide-react";
import type { Frame } from "../lib/types";

interface FrameStageProps {
  frame: Frame | null;
  zoom: boolean;
  onToggleZoom: () => void;
  // Mesma fonte usada no Filmstrip e no painel "A IA sugere" — um selo, um dado.
  isAnnotated: boolean;
}

const glass =
  "backdrop-blur-sm bg-black/50 border border-white/10 rounded-xl text-white";

function bboxColor(clsConf: number): string {
  if (clsConf >= 0.5) return "#34C759";
  if (clsConf >= 0.3) return "#FF9500";
  return "#8E8E93";
}

export function FrameStage({ frame, zoom, onToggleZoom, isAnnotated }: FrameStageProps) {
  const imgRef       = useRef<HTMLImageElement>(null);
  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const det        = frame?.detection ?? null;
  const confidence = det ? Math.round(det.cls_conf * 100) : 0;

  // Desenha bbox escalada no canvas, respeitando object-fit: contain
  const drawBbox = useCallback(() => {
    const canvas    = canvasRef.current;
    const img       = imgRef.current;
    const container = containerRef.current;
    if (!canvas || !img || !container) return;

    const cW = container.clientWidth;
    const cH = container.clientHeight;
    canvas.width  = cW;
    canvas.height = cH;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, cW, cH);

    // Limpa e sai cedo se este frame não tem detecção — sem isso o retângulo
    // do frame anterior ficava "grudado" no canvas (nunca era limpo).
    if (!det) return;

    const natW = img.naturalWidth;
    const natH = img.naturalHeight;
    if (!natW || !natH) return;

    // Escala para object-fit: contain
    const scale   = Math.min(cW / natW, cH / natH);
    const dispW   = natW * scale;
    const dispH   = natH * scale;
    const offsetX = (cW - dispW) / 2;
    const offsetY = (cH - dispH) / 2;

    // Quando zoom está ativo, recorta ao redor da bbox antes de exibir.
    // Nesse caso, o canvas mostra a imagem toda (sem crop no DOM),
    // então desenhamos a bbox sem ajuste extra de crop.
    // bboxNormalized (pipeline AWS/MegaDetector): [x, y, w, h] em 0-1 → converte para pixel-space.
    const [b0, b1, b2, b3] = det.bbox;
    const [x1, y1, x2, y2] = det.bboxNormalized
      ? [b0 * natW, b1 * natH, (b0 + b2) * natW, (b1 + b3) * natH]
      : [b0, b1, b2, b3];
    const sx1 = x1 * scale + offsetX;
    const sy1 = y1 * scale + offsetY;
    const bw  = (x2 - x1) * scale;
    const bh  = (y2 - y1) * scale;

    const color = bboxColor(det.cls_conf);

    // Retângulo
    ctx.strokeStyle = color;
    ctx.lineWidth   = 2.5;
    ctx.strokeRect(sx1, sy1, bw, bh);

    // Fundo semitransparente interno
    ctx.fillStyle = color + "18";
    ctx.fillRect(sx1, sy1, bw, bh);

    // Label
    const label = `${det.genus_pt}  ${confidence}%`;
    const fontSize = Math.max(12, Math.round(cW / 70));
    ctx.font = `600 ${fontSize}px "IBM Plex Sans", sans-serif`;
    const tw  = ctx.measureText(label).width;
    const th  = fontSize;
    const pad = 5;

    const lx = sx1;
    const ly = sy1 > th + pad * 2 + 4 ? sy1 - th - pad * 2 - 2 : sy1 + 2;

    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(lx, ly, tw + pad * 2, th + pad * 2, 5);
    ctx.fill();

    ctx.fillStyle = "#fff";
    ctx.fillText(label, lx + pad, ly + th + pad - 1);
  }, [det, confidence]);

  // Redesenha sempre que a detecção do frame atual mudar. O <img> abaixo tem
  // key={frame.path}, então a cada troca de frame é um nó <img> novo (não o
  // mesmo reaproveitado) — isso garante que o evento onload sempre dispara,
  // em vez de depender de checar img.complete/naturalWidth num nó reciclado
  // (que ficava sujeito a corrida com o cache do navegador e travava o
  // desenho no primeiro frame carregado).
  useEffect(() => {
    drawBbox();
  }, [drawBbox]);

  // Redesenha ao redimensionar a janela
  useEffect(() => {
    const onResize = () => drawBbox();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [drawBbox]);

  return (
    <div
      ref={containerRef}
      className="flex-1 relative overflow-hidden"
      style={{
        background: "#1A1E1A",
        borderRadius: 16,
        boxShadow: "0 1px 2px rgba(34,31,26,0.06), 0 10px 30px rgba(34,31,26,0.08)",
        minHeight: 0,
      }}
    >
      {frame ? (
        <>
          {/* Imagem — contain para não cortar a bbox */}
          <img
            key={frame.path}
            ref={imgRef}
            src={frame.imageUrl ?? `/api/image?p=${encodeURIComponent(frame.path)}`}
            alt={`Frame ${frame.idx}`}
            className="w-full h-full"
            style={{ objectFit: "contain" }}
            onLoad={drawBbox}
          />
          {/* Canvas de bbox — sobreposição absoluta */}
          <canvas
            ref={canvasRef}
            className="absolute inset-0 pointer-events-none"
            style={{ width: "100%", height: "100%" }}
          />
        </>
      ) : (
        <div className="w-full h-full flex items-center justify-center">
          <span className="text-white/30 text-sm font-medium">Nenhum frame</span>
        </div>
      )}

      {/* Selo de revisado + timestamp — cluster sup esq, lado a lado (sem sobrepor) */}
      {frame && (
        <div className="absolute top-3 left-3 flex items-center gap-1.5">
          {isAnnotated && (
            <div
              className="flex items-center justify-center rounded-full shrink-0"
              style={{ width: 30, height: 30, background: "#2D8B5F", boxShadow: "0 2px 8px rgba(0,0,0,0.3)" }}
              title="Frame revisado"
            >
              <Check size={16} color="#fff" strokeWidth={3} />
            </div>
          )}
          <div
            className={`${glass} px-3 py-1.5 text-xs`}
            style={{ fontFamily: "IBM Plex Mono, monospace", letterSpacing: "0.04em" }}
          >
            {frame.timestamp}
          </div>
        </div>
      )}

      {/* Botões zoom — sup dir */}
      <div className="absolute top-3 right-3 flex gap-1.5">
        <button
          onClick={onToggleZoom}
          className={`${glass} flex items-center justify-center transition-colors hover:bg-white/20`}
          style={{ width: 38, height: 38, borderRadius: 10 }}
          title={zoom ? "Sair do zoom" : "Zoom"}
        >
          <ZoomIn size={16} />
        </button>
        <button
          className={`${glass} flex items-center justify-center transition-colors hover:bg-white/20`}
          style={{ width: 38, height: 38, borderRadius: 10 }}
          title="Expandir"
        >
          <Maximize2 size={16} />
        </button>
      </div>

      {/* Chip IA — inf esq */}
      {det && (
        <div
          className={`${glass} absolute bottom-3 left-3 flex items-center gap-2.5 px-3 py-2`}
          style={{ fontSize: 13 }}
        >
          <span className="relative flex">
            <span
              className="absolute inline-flex h-full w-full rounded-full opacity-50 animate-ping"
              style={{ background: "#5FD08A" }}
            />
            <span
              className="relative inline-flex rounded-full"
              style={{ width: 8, height: 8, background: "#5FD08A" }}
            />
          </span>
          <span className="font-medium">
            IA ·{" "}
            <span className="font-semibold">{det.genus_pt}</span>{" "}
            <span className="text-white/55 text-xs italic">({det.genus})</span>
          </span>
          <span className="font-bold text-sm" style={{ color: "#E2A33C" }}>
            {confidence}%
          </span>
          <span className="text-white/45 text-xs">
            det {det.det_conf.toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
}
