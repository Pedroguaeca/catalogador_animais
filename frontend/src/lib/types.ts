export interface Detection {
  genus: string;
  genus_pt: string;
  det_conf: number;
  cls_conf: number;
  bbox: [number, number, number, number]; // x1 y1 x2 y2
}

export interface Frame {
  idx: number;          // frame number in video
  path: string;        // relative path from /api/image?p=...
  timestamp: string;   // "DD-MM-YYYY · HH:MM:SS"
  date: string;
  time: string;
  detection: Detection | null;
  status: "detection" | "review" | "empty"; // for filmstrip dot
}

export interface Video {
  id: string;   // e.g. "Cutia_Cam2Pos2_03"
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
  | { type: "SET_VIDEO"; payload: string }
  | { type: "NEXT_VIDEO" }
  | { type: "PREV_VIDEO" }
  | { type: "OPEN_NEW_CAT" }
  | { type: "CLOSE_NEW_CAT" }
  | { type: "SET_NEW_CAT_NAME"; payload: string }
  | { type: "ADD_CATEGORY"; payload: string }
  | { type: "MARK_ANNOTATED" };

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
