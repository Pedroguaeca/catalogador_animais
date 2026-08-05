// Vídeo listado em GET /projects/{id}/videos — ver backend/api.py:list_videos.
// Campos base existem desde sempre; os campos abaixo de "SIAB-105" foram
// adicionados pra alimentar a tela /videos por abas de status (thumbnail,
// confiança, sugestões da IA pré-revisão e rastreabilidade de revisor).
export interface VideoItem {
  video_id:          string;
  original_filename: string | null;
  camera_id:         string | null;
  captured_at:       string | null;
  uploaded_at:       string | null;
  status:            string | null;
  display_status:    string; // Processando | Aguardando revisão | Revisado | Sem detecção
  species:           string[]; // espécies confirmadas (vazio até a revisão humana)
  appearance_count:  number;

  // SIAB-105
  ai_species:    string[];      // sugestões da IA por frame, antes de confirmação humana
  confidence:    number | null; // 0–1; null quando não há dado (Processando/Sem detecção)
  thumbnail_url: string | null; // presigned URL do frame de maior ai_score
  reviewed_by:   string | null; // sub do JWT do revisor mais recente
  reviewed_at:   string | null; // timestamp ISO da revisão mais recente
  temperature_c: number | null; // OCR do overlay da câmera
}
