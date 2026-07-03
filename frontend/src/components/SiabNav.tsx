"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { UploadCloud, ClipboardList, Download, LayoutGrid, BarChart2, PlusCircle } from "lucide-react";

const links = [
  { href: "/",          label: "Anotação",   icon: LayoutGrid },
  { href: "/upload",    label: "Upload",     icon: UploadCloud },
  { href: "/review",    label: "Revisão",    icon: ClipboardList },
  { href: "/dashboard", label: "Dashboard",  icon: BarChart2 },
  { href: "/export",    label: "Exportar",   icon: Download },
];

export function SiabNav() {
  const pathname = usePathname();

  return (
    <header
      className="flex items-center gap-5 px-5 border-b bg-white shrink-0"
      style={{ height: 60, borderColor: "#EFE8DB" }}
    >
      {/* Logo */}
      <Link href="/" style={{ textDecoration: "none", display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 30, height: 30, background: "#2F6B4F", borderRadius: 9,
            boxShadow: "0 0 0 2px #fff, 0 0 0 3.5px #2F6B4F",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "#fff", fontWeight: 700, fontSize: 12,
            fontFamily: "Libre Franklin, sans-serif",
          }}
        >S</div>
        <span style={{ color: "#221F1A", fontWeight: 600, fontSize: 14, fontFamily: "IBM Plex Sans, sans-serif" }}>
          SIAB
        </span>
      </Link>

      <div style={{ width: 1, height: 22, background: "#E7DECF" }} />

      <nav className="flex items-center gap-1">
        {links.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "6px 12px", borderRadius: 10, textDecoration: "none",
                fontSize: 13, fontWeight: active ? 600 : 400,
                color:      active ? "#2F6B4F" : "#6B6357",
                background: active ? "#EEF5F0" : "transparent",
                fontFamily: "IBM Plex Sans, sans-serif",
                transition: "background 0.15s, color 0.15s",
              }}
            >
              <Icon size={14} />
              {label}
            </Link>
          );
        })}
      </nav>

      <div style={{ flex: 1 }} />

      <Link
        href="/upload"
        style={{
          display: "flex", alignItems: "center", gap: 6,
          padding: "6px 12px", borderRadius: 10, textDecoration: "none",
          fontSize: 13, fontWeight: 500,
          color: "#2F6B4F", background: "#EEF5F0",
          border: "1.5px solid #CDE3D6",
          fontFamily: "IBM Plex Sans, sans-serif",
          transition: "background 0.15s",
        }}
        onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#CDE3D6")}
        onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "#EEF5F0")}
      >
        <PlusCircle size={14} />
        Adicionar vídeos
      </Link>
    </header>
  );
}
