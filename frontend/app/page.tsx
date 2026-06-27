import { ReviewPage } from "../src/components/ReviewPage";
import { loadVideos } from "../src/lib/data";

export default function Home() {
  const videos = loadVideos();

  if (videos.length === 0) {
    return (
      <div
        className="h-screen flex flex-col items-center justify-center gap-4"
        style={{ background: "#FAF6EE", fontFamily: "IBM Plex Sans, sans-serif" }}
      >
        <div className="flex items-center gap-3">
          <div
            style={{
              width: 30, height: 30, background: "#2F6B4F", borderRadius: 9,
              boxShadow: "0 0 0 2px #fff, 0 0 0 3.5px #2F6B4F",
            }}
          />
          <span className="text-lg font-semibold" style={{ color: "#221F1A" }}>
            SIAB / Revisão
          </span>
        </div>
        <p className="text-sm" style={{ color: "#6B6357" }}>
          Nenhum frame encontrado. Execute o pipeline primeiro.
        </p>
        <pre
          className="text-xs p-4 rounded-xl"
          style={{ background: "#EFE8DB", color: "#221F1A" }}
        >
          cd .. &amp;&amp; conda activate catalogo &amp;&amp; python main.py
        </pre>
      </div>
    );
  }

  return <ReviewPage videos={videos} />;
}
