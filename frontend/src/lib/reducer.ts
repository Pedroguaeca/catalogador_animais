import type { ReviewState, ReviewAction, Category } from "./types";

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

export const initialState = (videoId: string, totalFrames: number): ReviewState => ({
  query: "",
  selected: null,
  confirmed: false,
  newCatOpen: false,
  newCatName: "",
  annotated: 0,
  frameIdx: 1,
  videoId,
  categories: DEFAULT_CATEGORIES,
  annotatedFrames: new Set(),
});

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
      if (state.annotatedFrames.has(state.frameIdx)) return state;
      const next = new Set(state.annotatedFrames);
      next.add(state.frameIdx);
      return { ...state, annotatedFrames: next, annotated: state.annotated + 1 };
    }

    case "SET_FRAME":
      return { ...state, frameIdx: action.payload, selected: null, confirmed: false, query: "" };

    case "NEXT_FRAME":
      return { ...state, frameIdx: state.frameIdx + 1, selected: null, confirmed: false, query: "" };

    case "PREV_FRAME":
      return { ...state, frameIdx: Math.max(1, state.frameIdx - 1), selected: null, confirmed: false, query: "" };

    case "SKIP_FRAME":
      return { ...state, frameIdx: state.frameIdx + 1, selected: null, confirmed: false, query: "" };

    case "SET_VIDEO":
      return { ...state, videoId: action.payload, frameIdx: 1, selected: null, confirmed: false, query: "" };

    case "OPEN_NEW_CAT":
      return { ...state, newCatOpen: true, newCatName: "" };

    case "CLOSE_NEW_CAT":
      return { ...state, newCatOpen: false, newCatName: "" };

    case "SET_NEW_CAT_NAME":
      return { ...state, newCatName: action.payload };

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
