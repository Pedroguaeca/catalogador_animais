"use client";

interface BottomBarProps {
  videoIdx: number;
  totalVideos: number;
  onPrevVideo: () => void;
  onNextVideo: () => void;
}

const font = { fontFamily: "IBM Plex Sans, sans-serif" };

function NavBtn({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium rounded-xl disabled:opacity-30 disabled:cursor-not-allowed"
      style={{
        background: "#FAF6EE",
        color: "#221F1A",
        border: "1.5px solid #E7DECF",
        borderRadius: 10,
        fontSize: 13,
        transition: "background 0.15s",
        ...font,
      }}
      onMouseEnter={(e) => {
        if (!disabled) (e.currentTarget as HTMLElement).style.background = "#EFE8DB";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.background = "#FAF6EE";
      }}
    >
      {children}
    </button>
  );
}

export function BottomBar({ videoIdx, totalVideos, onPrevVideo, onNextVideo }: BottomBarProps) {
  return (
    <footer
      className="flex items-center justify-between px-5 border-t bg-white shrink-0"
      style={{ height: 52 }}
    >
      <NavBtn onClick={onPrevVideo} disabled={videoIdx === 0}>
        ◄◄ Vídeo anterior
      </NavBtn>
      <span className="text-xs" style={{ color: "#C3BAA8", ...font }}>
        Vídeo {videoIdx + 1} / {totalVideos}
      </span>
      <NavBtn onClick={onNextVideo} disabled={videoIdx >= totalVideos - 1}>
        Vídeo seguinte ▶▶
      </NavBtn>
    </footer>
  );
}
