import { NextRequest, NextResponse } from "next/server";
import path from "path";
import fs from "fs";

import { getFramesRoot } from "../../../src/lib/data";
const FRAMES_ROOT = getFramesRoot();

export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams.get("p");
  if (!p) return new NextResponse("Missing path", { status: 400 });

  // Sanitize: prevent path traversal
  const normalized = path.normalize(p).replace(/^(\.\.(\/|\\|$))+/, "");
  const abs = path.join(FRAMES_ROOT, normalized);

  if (!abs.startsWith(FRAMES_ROOT)) {
    return new NextResponse("Forbidden", { status: 403 });
  }

  if (!fs.existsSync(abs)) {
    return new NextResponse("Not found", { status: 404 });
  }

  const buf = fs.readFileSync(abs);
  return new NextResponse(buf, {
    headers: {
      "Content-Type": "image/jpeg",
      "Cache-Control": "public, max-age=86400",
    },
  });
}
