"use client";

import { useEffect, useRef, useState } from "react";
import { Info } from "lucide-react";

interface InfoTooltipProps {
  text: string;
}

const font = { fontFamily: "IBM Plex Sans, sans-serif" };

// Ícone de info clicável (não hover) — mesmo padrão de click-outside já usado
// em TopBar.tsx (VideoDropdown), sem lib nova.
export function InfoTooltip({ text }: InfoTooltipProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative inline-flex" style={{ lineHeight: 0 }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Mais informações"
        className="flex items-center justify-center"
        style={{ color: "#3A7CA5", cursor: "pointer" }}
      >
        <Info size={13} />
      </button>

      {open && (
        <div
          className="absolute z-20 text-xs"
          style={{
            top: "calc(100% + 8px)",
            left: "50%",
            transform: "translateX(-50%)",
            width: 160,
            padding: "10px 12px",
            borderRadius: 10,
            background: "#221F1A",
            color: "#FAF6EE",
            boxShadow: "0 4px 20px rgba(34,31,26,0.25)",
            lineHeight: 1.4,
            ...font,
          }}
        >
          {text}
        </div>
      )}
    </div>
  );
}
