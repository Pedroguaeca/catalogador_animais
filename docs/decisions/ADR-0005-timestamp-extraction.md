# ADR-0005 — Extração de timestamp e camera_id: metadados + OCR com fallback manual

**Status:** Aceito | **Data:** Julho 2026

## Contexto
Os vídeos de câmera-armadilha precisam ter timestamp e camera_id extraídos 
automaticamente para rastreabilidade das aparições. Amostrados 3 vídeos reais 
de 2 modelos Bushnell diferentes — nenhum continha metadados EXIF ou MP4 
(creation_time, DateTimeOriginal). Todos tinham overlay visual na barra inferior 
com os dados gravados como pixels.

## Decisão
Estratégia de três estágios com fallback:

1. **Metadados do arquivo** — tenta ler EXIF/MP4 via ffprobe. 
   Marca location_source="metadata" se encontrar.
2. **OCR no overlay visual** — recorta os últimos 12% da altura do frame,
   roda easyocr, parseia o padrão Bushnell:
   [cam_id 4 dígitos] [ícones] [temp°C] [temp°F] [dd/mm/yyyy] [hh:mm:ss] [seq]
   Marca location_source="ocr" se encontrar.
3. **Manual** — campos ficam None, location_source="manual". 
   Analista preenche via frontend.

## Quirks do easyocr com overlay Bushnell (documentados nos testes)
- Pixel threshold para detectar barra escura: < 80 (não < 50)
- easyocr insere espaço dentro de pares de dígitos antes de barra: "0 1/" → normalizar para "01/"
- easyocr converte "°" em "%" e omite "C": usar fallback regex \d+ % com range −30..60°C

## Resultado do teste com vídeo real
DSCF0007.AVI (câmera Bushnell, diurno):
- camera_id: "0004" ✅
- captured_at: "2025-01-11T08:14:30" ✅  
- temperature_c: 19.0 ✅
- location_source: "ocr" ✅

## Consequências
- O ingester chama extract_video_metadata() antes de publicar na fila SQS
- camera_id extraído pelo OCR é sugerido na UI de cadastro de câmera
- Câmeras de outras marcas podem ter overlay diferente — parser pode precisar 
  de extensão futura por modelo de câmera
- Câmeras com metadados EXIF (marcas mais modernas) serão cobertas pelo estágio 1
