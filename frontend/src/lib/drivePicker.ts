declare global {
  interface Window {
    gapi: any;
    google: any;
  }
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
    const s = document.createElement("script");
    s.src = src;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(`Falha ao carregar ${src}`));
    document.head.appendChild(s);
  });
}

async function ensureGapi(): Promise<void> {
  await loadScript("https://apis.google.com/js/api.js");
  await new Promise<void>((resolve) => {
    if (window.gapi.picker) { resolve(); return; }
    window.gapi.load("picker", { callback: resolve });
  });
}

async function ensureGis(): Promise<void> {
  await loadScript("https://accounts.google.com/gsi/client");
}

function getToken(clientId: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: "https://www.googleapis.com/auth/drive.readonly",
      callback: (resp: any) => {
        if (resp.error) reject(new Error(resp.error));
        else resolve(resp.access_token);
      },
    });
    client.requestAccessToken({ prompt: "consent" });
  });
}

export interface DriveFile {
  id: string;
  name: string;
  mimeType: string;
  sizeBytes: number;
}

export async function openDrivePicker(): Promise<DriveFile[]> {
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  const apiKey   = process.env.NEXT_PUBLIC_GOOGLE_API_KEY;

  if (!clientId || !apiKey || clientId.includes("SEU_")) {
    throw new Error(
      "Configure NEXT_PUBLIC_GOOGLE_CLIENT_ID e NEXT_PUBLIC_GOOGLE_API_KEY no arquivo frontend/.env.local"
    );
  }

  await Promise.all([ensureGapi(), ensureGis()]);
  const token = await getToken(clientId);

  return new Promise((resolve, reject) => {
    const VIDEO_MIME = [
      "video/mp4", "video/x-msvideo", "video/quicktime",
      "video/x-matroska", "video/webm", "video/x-ms-wmv",
      "video/3gpp", "video/MP2T",
    ].join(",");

    const view = new window.google.picker.DocsView(window.google.picker.ViewId.DOCS)
      .setMimeTypes(VIDEO_MIME)
      .setMode(window.google.picker.DocsViewMode.LIST);

    const picker = new window.google.picker.PickerBuilder()
      .addView(view)
      .setOAuthToken(token)
      .setDeveloperKey(apiKey)
      .setTitle("Selecionar vídeos para o SIAB")
      .enableFeature(window.google.picker.Feature.MULTISELECT_ENABLED)
      .setCallback((data: any) => {
        if (data.action === window.google.picker.Action.CANCEL) {
          resolve([]);
          return;
        }
        if (data.action !== window.google.picker.Action.PICKED) return;
        resolve(
          (data.docs ?? []).map((d: any) => ({
            id:        d.id,
            name:      d.name,
            mimeType:  d.mimeType,
            sizeBytes: d.sizeBytes ?? 0,
          }))
        );
      })
      .build();

    picker.setVisible(true);
  });
}

export async function downloadDriveFile(
  fileId: string,
  fileName: string,
  mimeType: string,
  onProgress?: (pct: number) => void
): Promise<File> {
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID!;
  await ensureGis();
  const token = await getToken(clientId);

  const url = `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media`;
  const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });

  if (!resp.ok) throw new Error(`Erro ao baixar do Drive: ${resp.status}`);

  const total  = Number(resp.headers.get("content-length") ?? 0);
  const reader = resp.body!.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.length;
    if (total > 0) onProgress?.(Math.round((received / total) * 100));
  }

  const blob = new Blob(chunks as BlobPart[], { type: mimeType });
  return new File([blob], fileName, { type: mimeType });
}
