import type { ReviewState, ReviewAction, Category, Frame } from "./types";

// Frames com status "detection" chegam da API já anotados (annotated_species presente).
// Usado para semear o progresso real ao carregar/trocar de vídeo, em vez de assumir 0.
function preAnnotatedIndices(frames: Frame[]): Set<number> {
  return new Set(frames.filter((f) => f.status === "detection").map((f) => f.idx));
}

// Espécie confirmada por posição de frame, semeada do fetch inicial — mesma
// lógica de preAnnotatedIndices, mas guardando o nome pra exibir "Revisado: X".
function preAnnotatedSpecies(frames: Frame[]): Record<number, string> {
  const map: Record<number, string> = {};
  for (const f of frames) {
    if (f.status === "detection" && f.annotatedSpecies) map[f.idx] = f.annotatedSpecies;
  }
  return map;
}

export const DEFAULT_CATEGORIES: Category[] = [
  { id: "aramides",     name: "Aramides" },
  { id: "crypturellus", name: "Crypturellus" },
  { id: "cutia",        name: "Cutia" },
  { id: "dasyprocta",   name: "Dasyprocta" },
  { id: "irara",        name: "Irara" },
  { id: "macuco",       name: "Macuco" },
  { id: "pecari",       name: "Cateto" },
  { id: "teiu",         name: "Teiú" },
  { id: "tinamus",      name: "Tinamus" },
  { id: "paca",         name: "Paca" },
  { id: "quati",        name: "Quati" },
  { id: "anta",         name: "Anta" },
];

export const initialState = (videoId: string, frames: Frame[]): ReviewState => {
  const annotatedFrames = preAnnotatedIndices(frames);
  return {
    query: "",
    selected: null,
    confirmed: false,
    newCatOpen: false,
    newCatName: "",
    annotated: annotatedFrames.size,
    frameIdx: 1,
    videoId,
    categories: DEFAULT_CATEGORIES,
    annotatedFrames,
    annotatedSpecies: preAnnotatedSpecies(frames),
  };
};

export function reviewReducer(state: ReviewState, action: ReviewAction): ReviewState {
  switch (action.type) {
    case "SET_QUERY":
      return { ...state, query: action.payload };

    case "SELECT":
      return { ...state, selected: action.payload, confirmed: false };

    case "CONFIRM_AI":
      return { ...state, confirmed: true };

    case "REJECT":
      return { ...state, selected: null, confirmed: false };

    case "MARK_ANNOTATED": {
      const alreadyMarked = state.annotatedFrames.has(state.frameIdx);
      const next = alreadyMarked ? state.annotatedFrames : new Set(state.annotatedFrames).add(state.frameIdx);
      return {
        ...state,
        annotatedFrames: next,
        annotated: alreadyMarked ? state.annotated : state.annotated + 1,
        annotatedSpecies: { ...state.annotatedSpecies, [state.frameIdx]: action.payload.species },
      };
    }

    case "SET_FRAME":
      return { ...state, frameIdx: action.payload, selected: null, confirmed: false, query: "" };

    case "NEXT_FRAME":
      return { ...state, frameIdx: state.frameIdx + 1, selected: null, confirmed: false, query: "" };

    case "PREV_FRAME":
      return { ...state, frameIdx: Math.max(1, state.frameIdx - 1), selected: null, confirmed: false, query: "" };

    case "SKIP_FRAME":
      return { ...state, frameIdx: state.frameIdx + 1, selected: null, confirmed: false, query: "" };

    case "SET_VIDEO": {
      const annotatedFrames = preAnnotatedIndices(action.payload.frames);
      return {
        ...state,
        videoId: action.payload.videoId,
        frameIdx: 1,
        selected: null,
        confirmed: false,
        query: "",
        annotatedFrames,
        annotated: annotatedFrames.size,
        annotatedSpecies: preAnnotatedSpecies(action.payload.frames),
      };
    }

    case "OPEN_NEW_CAT":
      return { ...state, newCatOpen: true, newCatName: "" };

    case "CLOSE_NEW_CAT":
      return { ...state, newCatOpen: false, newCatName: "" };

    case "SET_NEW_CAT_NAME":
      return { ...state, newCatName: action.payload };

    case "CONFIRM_ALL_VIDEO": {
      const { frames } = action.payload;
      const next = new Set(state.annotatedFrames);
      const nextSpecies = { ...state.annotatedSpecies };
      for (const f of frames) {
        next.add(f.idx);
        // "Confirmar vídeo" aplica o palpite da IA a cada frame — só sobrescreve
        // o nome exibido se ainda não havia correção humana anterior pro frame.
        if (f.detection && nextSpecies[f.idx] === undefined) nextSpecies[f.idx] = f.detection.genus_pt;
      }
      return { ...state, annotatedFrames: next, annotated: next.size, annotatedSpecies: nextSpecies, confirmed: true };
    }

    case "ADD_CATEGORY": {
      const name = action.payload.trim();
      if (!name) return state;
      const id = name.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
      const exists = state.categories.find((c) => c.name.toLowerCase() === name.toLowerCase());
      if (exists) return { ...state, selected: exists.id, newCatOpen: false, newCatName: "" };
      const newCat: Category = { id, name };
      return {
        ...state,
        categories: [newCat, ...state.categories],
        selected: id,
        confirmed: false,
        newCatOpen: false,
        newCatName: "",
      };
    }

    default:
      return state;
  }
}
