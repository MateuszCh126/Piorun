import json
import os
import base64
from datetime import datetime
from core.config import get_settings

# KONFIGURACJA
SETTINGS = get_settings()
SESSIONS_ROOT = str(SETTINGS.sessions_root)
NOTES_ROOT = str(SETTINGS.notes_root)

CSS_STYLE = """
:root {
  --bg: #0d1117;
  --surface: #161b22;
  --border: #30363d;
  --text: #c9d1d9;
  --accent: #f0c040;
  --heading: #ffffff;
}
body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; display: flex; line-height: 1.6; }
.sidebar { width: 280px; background: var(--surface); border-right: 1px solid var(--border); height: 100vh; overflow-y: auto; position: sticky; top: 0; padding: 25px; box-sizing: border-box; }
.content { flex: 1; padding: 50px; max-width: 1000px; margin: 0 auto; }
.chunk { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 30px; margin-bottom: 40px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
.chunk-header { color: var(--accent); font-size: 0.85em; font-weight: bold; margin-bottom: 15px; text-transform: uppercase; letter-spacing: 1px; }
.slide-thumb { max-width: 400px; width: 100%; border-radius: 8px; float: right; margin-left: 20px; margin-bottom: 20px; border: 1px solid var(--border); transition: transform 0.3s; cursor: pointer; }
.slide-thumb:hover { transform: scale(1.05); }
h1 { color: var(--heading); border-bottom: 2px solid var(--border); padding-bottom: 10px; }
h2 { color: var(--heading); margin-top: 0; }
h3 { color: var(--accent); font-size: 1.1em; }
strong { color: var(--accent); }
hr { border: 0; border-top: 1px solid var(--border); margin: 30px 0; }
ul { padding-left: 20px; }
li { margin-bottom: 8px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.badge { background: var(--border); padding: 4px 8px; border-radius: 4px; font-size: 0.8em; margin-right: 5px; }
"""

def image_to_base64(path):
    if not os.path.exists(path): return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def markdown_to_html_simple(md):
    # Prosta konwersja Markdown na HTML bez bibliotek
    lines = md.split('\n')
    html = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_list: 
                html.append("</ul>")
                in_list = False
            continue
            
        # Naglowki
        if line.startswith('## '): line = f"<h2>{line[3:]}</h2>"
        elif line.startswith('### '): line = f"<h3>{line[4:]}</h3>"
        
        # Pogrubienie
        while '**' in line:
            line = line.replace('**', '<strong>', 1).replace('**', '</strong>', 1)
        
        # Listy
        if line.startswith('- '):
            if not in_list:
                html.append("<ul>")
                in_list = True
            line = f"<li>{line[2:]}</li>"
        elif in_list:
            html.append("</ul>")
            in_list = False
            
        html.append(line)
    
    if in_list: html.append("</ul>")
    return "\n".join(html)

def build_lecture_page(session_dir, subject):
    notes_json = os.path.join(session_dir, "notes_structured.json")
    if not os.path.exists(notes_json): return None
    
    with open(notes_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    date_str = os.path.basename(session_dir).split('_')[0]
    
    html = [f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Piorun ⚡ Notatki: {subject} ({date_str})</title>
    <style>{CSS_STYLE}</style>
</head>
<body>
<nav class="sidebar">
    <h2 style="color:var(--accent); font-size: 1.2em;">⚡ PIORUN ACADEMIC</h2>
    <hr>
    <div style="font-size: 0.9em;">
        <p><strong>PRZEDMIOT:</strong><br>{subject}</p>
        <p><strong>DATA:</strong><br>{date_str}</p>
    </div>
    <hr>
    <a href="../index.html">← Powrót do bazy</a>
</nav>
<main class="content">
    <h1>{subject} — Wykład z dnia {date_str}</h1>
"""]

    for chunk in data:
        time_display = f"{chunk['time_start'] // 60:02d}:{chunk['time_start'] % 60:02d}"
        
        slide_html = ""
        if chunk['slide']:
            slide_path = os.path.join(session_dir, chunk['slide'])
            b64 = image_to_base64(slide_path)
            if b64:
                slide_html = f'<img class="slide-thumb" src="data:image/png;base64,{b64}" onclick="window.open(this.src)">'
        
        notes_html = markdown_to_html_simple(chunk['notes_markdown'])
        
        html.append(f"""
    <div class="chunk">
        <div class="chunk-header"><span class="badge">Sekcja</span> Czas: {time_display}</div>
        {slide_html}
        <div class="notes-body">
            {notes_html}
        </div>
        <div style="clear:both;"></div>
    </div>
""")

    html.append("</main></body></html>")
    
    # Zapisz HTML
    obj_dir = os.path.join(NOTES_ROOT, subject)
    os.makedirs(obj_dir, exist_ok=True)
    file_path = os.path.join(obj_dir, f"{date_str}.html")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(html))
    
    update_index()
    return file_path

def update_index():
    subjects = [d for d in os.listdir(NOTES_ROOT) if os.path.isdir(os.path.join(NOTES_ROOT, d)) and d != "index_files"]
    
    html = [f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <title>Piorun ⚡ Baza Wiedzy Akademickiej</title>
    <style>{CSS_STYLE}
    .subject-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 25px; margin-bottom: 20px; }}
    .lecture-link {{ display: block; padding: 10px; border-radius: 6px; margin: 5px 0; background: var(--bg); transition: 0.2s; }}
    .lecture-link:hover {{ border-color: var(--accent); background: #1c2128; }}
    </style>
</head>
<body>
<nav class="sidebar">
    <h2 style="color:var(--accent); font-size: 1.2em;">⚡ PIORUN ACADEMIC</h2>
    <hr>
    <p style="font-size: 0.8em; opacity: 0.7;">Witaj w swojej autonomicznej bazie wiedzy. Twoje notatki są generowane automatycznie przez Pioruna.</p>
</nav>
<main class="content">
    <h1>Baza Wiedzy Akademickiej</h1>
    <input type="text" id="searchBox" placeholder="Szukaj: przedmiot lub data…"
           style="width:100%; box-sizing:border-box; padding:12px; margin-bottom:25px;
                  background:var(--surface); border:1px solid var(--border);
                  border-radius:8px; color:var(--text); font-size:1em;">
    <p id="noResults" style="display:none; opacity:0.6;">Brak pasujących wykładów.</p>
"""]

    if not subjects:
        html.append("<p>Brak nagranych wykładów. Użyj komendy /lecture w terminalu Pioruna, aby zacząć.</p>")
    
    for sub in sorted(subjects):
        html.append(f'<div class="subject-card"><h2>📚 {sub}</h2>')
        lectures = sorted(os.listdir(os.path.join(NOTES_ROOT, sub)), reverse=True)
        for lec in lectures:
            if lec.endswith(".html"):
                date_only = lec.replace(".html", "")
                html.append(f'<a href="{sub}/{lec}" class="lecture-link">🗓️ Wykład z dnia {date_only}</a>')
        html.append('</div>')

    html.append("""
    <script>
    (function () {
      var box = document.getElementById('searchBox');
      if (!box) return;
      var cards = Array.prototype.slice.call(document.querySelectorAll('.subject-card'));
      var noResults = document.getElementById('noResults');
      box.addEventListener('input', function () {
        var q = box.value.trim().toLowerCase();
        var anyVisible = false;
        cards.forEach(function (card) {
          var links = Array.prototype.slice.call(card.querySelectorAll('.lecture-link'));
          var heading = (card.querySelector('h2') || {}).textContent || '';
          var subjectMatch = heading.toLowerCase().indexOf(q) !== -1;
          var visibleLinks = 0;
          links.forEach(function (a) {
            var show = subjectMatch || a.textContent.toLowerCase().indexOf(q) !== -1 || q === '';
            a.style.display = show ? '' : 'none';
            if (show) visibleLinks++;
          });
          var showCard = q === '' || subjectMatch || visibleLinks > 0;
          card.style.display = showCard ? '' : 'none';
          if (showCard) anyVisible = true;
        });
        if (noResults) noResults.style.display = anyVisible ? 'none' : 'block';
      });
    })();
    </script>
    """)
    html.append("</main></body></html>")

    with open(os.path.join(NOTES_ROOT, "index.html"), 'w', encoding='utf-8') as f:
        f.write("\n".join(html))

if __name__ == "__main__":
    # Testowy update indexu
    os.makedirs(NOTES_ROOT, exist_ok=True)
    update_index()
    print(f"[OK] Dashboard zaktualizowany: {os.path.join(NOTES_ROOT, 'index.html')}")
