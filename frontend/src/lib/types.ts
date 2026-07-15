export interface Detection {
  genus: string;
  genus_pt: string;
  det_conf: number;
  cls_conf: number;
  bbox: [number, number, number, number]; // x1 y1 x2 y2 (pixel-space) — ou x,y,w,h normalizado 0-1 se bboxNormalized
  bboxNormalized?: boolean; // true para dados vindos do pipeline AWS (MegaDetector, 0-1)
}

export interface Frame {
  idx: number;          // frame number in video
  path: string;        // relative path from /api/image?p=... (fallback quando imageUrl ausente)
  imageUrl?: string;   // presigned S3 URL (dados AWS) — tem prioridade sobre path
  video_uuid: string;  // first segment of path = UUID used in S3 keys
  timestamp: string;   // "DD-MM-YYYY · HH:MM:SS"
  date: string;
  time: string;
  detection: Detection | null;
  status: "detection" | "review" | "empty"; // for filmstrip dot
}

export interface Video {
  id: string;   // e.g. "Cutia_Cam2Pos2_03"
  original_filename?: string | null;
  display_status?: string; // mesmos valores de GET /videos: Processando/Aguardando revisão/Revisado/Sem detecção
  frames: Frame[];
}

export interface Category {
  id: string;
  name: string; // Portuguese name
}

export type ReviewAction =
  | { type: "SET_QUERY"; payload: string }
  | { type: "SELECT"; payload: string }
  | { type: "CONFIRM_AI" }
  | { type: "REJECT" }
  | { type: "SET_FRAME"; payload: number }
  | { type: "NEXT_FRAME" }
  | { type: "PREV_FRAME" }
  | { type: "SKIP_FRAME" }
  | { type: "SET_VIDEO"; payload: { videoId: string; frames: Frame[] } }
  | { type: "NEXT_VIDEO" }
  | { type: "PREV_VIDEO" }
  | { type: "OPEN_NEW_CAT" }
  | { type: "CLOSE_NEW_CAT" }
  | { type: "SET_NEW_CAT_NAME"; payload: string }
  | { type: "ADD_CATEGORY"; payload: string }
  | { type: "MARK_ANNOTATED" }
  | { type: "CONFIRM_ALL_VIDEO"; payload: number };

export interface ReviewState {
  query: string;
  selected: string | null;
  confirmed: boolean;
  newCatOpen: boolean;
  newCatName: string;
  annotated: number;
  frameIdx: number;    // 1-based
  videoId: string;
  categories: Category[];
  annotatedFrames: Set<number>;
}
