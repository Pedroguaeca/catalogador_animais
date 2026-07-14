import { ReviewPage } from "../src/components/ReviewPage";
import { SiabNav } from "../src/components/SiabNav";
import { loadVideos } from "../src/lib/data";

export default function Home() {
  const videos = loadVideos();

  if (videos.length === 0) {
    return (
      <div className="flex flex-col h-screen overflow-hidden" style={{ fontFamily: "IBM Plex Sans, sans-serif" }}>
        <SiabNav />
        <div
          className="flex-1 flex flex-col items-center justify-center gap-4"
          style={{ background: "#FAF6EE" }}
        >
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
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <SiabNav />
      <ReviewPage videos={videos} />
    </div>
  );
}
