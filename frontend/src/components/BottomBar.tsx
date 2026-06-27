"use client";

interface BottomBarProps {
  frameIdx: number;
  totalFrames: number;
  videoIdx: number;
  totalVideos: number;
  onPrevFrame: () => void;
  onNextFrame: () => void;
  onSkipFrame: () => void;
  onPrevVideo: () => void;
  onNextVideo: () => void;
}

const font = { fontFamily: "IBM Plex Sans, sans-serif" };

function NavBtn({
  children,
  onClick,
  disabled,
  primary,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium rounded-xl transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
      style={{
        background: primary ? "#2F6B4F" : "#FAF6EE",
        color: primary ? "#fff" : "#221F1A",
        border: primary ? "none" : "1.5px solid #E7DECF",
        borderRadius: 10,
        fontSize: 13.5,
        ...font,
      }}
      onMouseEnter={(e) => {
        if (!disabled) {
          (e.currentTarget as HTMLElement).style.background = primary
            ? "#3E8E63"
            : "#EFE8DB";
        }
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.background = primary
          ? "#2F6B4F"
          : "#FAF6EE";
      }}
    >
      {children}
    </button>
  );
}

export function BottomBar({
  frameIdx,
  totalFrames,
  videoIdx,
  totalVideos,
  onPrevFrame,
  onNextFrame,
  onSkipFrame,
  onPrevVideo,
  onNextVideo,
}: BottomBarProps) {
  return (
    <footer
      className="flex items-center justify-between px-5 border-t bg-white shrink-0"
      style={{ height: 66 }}
    >
      <div className="flex items-center gap-2">
        <NavBtn onClick={onPrevVideo} disabled={videoIdx === 0}>
          ◄◄ Vídeo anterior
        </NavBtn>
        <NavBtn onClick={onPrevFrame} disabled={frameIdx <= 1}>
          ◄ Frame anterior
        </NavBtn>
      </div>

      {/* Centro */}
      <div className="flex flex-col items-center gap-0.5">
        <button
          onClick={onSkipFrame}
          disabled={frameIdx >= totalFrames}
          className="px-4 py-1.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-30"
          style={{
            background: "#FAF6EE",
            border: "1.5px solid #E7DECF",
            color: "#6B6357",
            borderRadius: 9,
            ...font,
          }}
        >
          Pular frame{" "}
          <kbd
            className="text-xs rounded px-1"
            style={{
              background: "#EFE8DB",
              color: "#9A9080",
              fontFamily: "IBM Plex Mono, monospace",
            }}
          >
            S
          </kbd>
        </button>
        <span className="text-xs" style={{ color: "#C3BAA8", ...font }}>
          ⏎ confirmar · ← → navegar
        </span>
      </div>

      <div className="flex items-center gap-2">
        <NavBtn
          onClick={onNextFrame}
          primary
          disabled={frameIdx >= totalFrames}
        >
          Frame seguinte ►
        </NavBtn>
        <NavBtn onClick={onNextVideo} disabled={videoIdx >= totalVideos - 1}>
          Vídeo seguinte ►►
        </NavBtn>
      </div>
    </footer>
  );
}
