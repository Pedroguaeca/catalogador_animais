# theme_utils.py — extrai cores dominantes do logo e monta CSS variables
import os
from colorthief import ColorThief

def _hex(rgb): return "#{:02x}{:02x}{:02x}".format(*rgb)

def palette_from_logo(logo_path="assets/logo.png"):
    if not os.path.exists(logo_path):
        # fallback: cores padrão
        return {
            "primary": "#2E8B57", "accent": "#0EA5E9", "muted": "#667085",
            "bg": "#FFFFFF", "bg2": "#F6F7F9", "danger": "#D92D20"
        }
    ct = ColorThief(logo_path)
    dom = ct.get_color(quality=4)                  # cor dominante
    pals = ct.get_palette(color_count=6, quality=6)

    primary = _hex(dom)
    # escolhe um acento que contraste com a primária
    accent = _hex(pals[1] if len(pals) > 1 else dom)
    # tom neutro (muted)
    muted = _hex(pals[2] if len(pals) > 2 else (120,120,120))
    return {
        "primary": primary,
        "accent": accent,
        "muted": muted,
        "bg": "#FFFFFF", "bg2": "#F6F7F9", "danger": "#D92D20"
    }

def css_vars_from_palette(pal):
    return f"""
    :root {{
      --primary: {pal['primary']};
      --accent:  {pal['accent']};
      --muted:   {pal['muted']};
      --bg:      {pal['bg']};
      --bg2:     {pal['bg2']};
      --danger:  {pal['danger']};
    }}
    """
