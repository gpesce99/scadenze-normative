"""
Scadenze normative — generatore dashboard
Legge i database Notion e produce index.html per GitHub Pages.

Variabili d'ambiente richieste:
  NOTION_API_KEY          — Integration token Notion
  NOTION_DEADLINES_DB_ID  — ID del database "Scadenze"
  NOTION_CLIENTS_DB_ID    — ID del database "Clienti" (già esistente)
"""

import os
import json
import urllib.request
import urllib.error
from datetime import date, datetime

# ── Configurazione ────────────────────────────────────────────────────────────

NOTION_API_KEY         = os.environ["NOTION_API_KEY"]
DEADLINES_DB_ID        = os.environ["NOTION_DEADLINES_DB_ID"]
CLIENTS_DB_ID          = os.environ["NOTION_CLIENTS_DB_ID"]
NOTION_VERSION         = "2022-06-28"

TIPO_CONFIG = {
    "Normativa":  {"color": "blue",   "icon": "📋"},
    "Cliente":    {"color": "teal",   "icon": "⚡"},
    "Incentivo":  {"color": "amber",  "icon": "💰"},
    "Periodica":  {"color": "purple", "icon": "🔄"},
}

COLOR_CSS = {
    "blue":   ("E6F1FB", "185FA5", "0C447C"),
    "teal":   ("E1F5EE", "0F6E56", "085041"),
    "amber":  ("FAEEDA", "854F0B", "633806"),
    "purple": ("EEEDFE", "534AB7", "3C3489"),
}

# ── Client Notion ─────────────────────────────────────────────────────────────

def notion_request(path, payload=None):
    url = f"https://api.notion.com/v1/{path}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {NOTION_API_KEY}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        method="POST" if payload else "GET",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def query_database(db_id, filter_obj=None):
    """Recupera tutte le pagine di un database (gestisce la paginazione)."""
    results = []
    payload = {"page_size": 100}
    if filter_obj:
        payload["filter"] = filter_obj
    cursor = None
    while True:
        if cursor:
            payload["start_cursor"] = cursor
        data = notion_request(f"databases/{db_id}/query", payload)
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return results

# ── Lettura proprietà Notion ──────────────────────────────────────────────────

def prop(page, name, kind):
    p = page.get("properties", {}).get(name, {})
    if kind == "title":
        items = p.get("title", [])
        return "".join(t.get("plain_text", "") for t in items).strip()
    if kind == "select":
        s = p.get("select")
        return s["name"] if s else ""
    if kind == "date":
        d = p.get("date")
        return d["start"] if d else None
    if kind == "relation":
        rels = p.get("relation", [])
        return [r["id"] for r in rels]
    if kind == "rich_text":
        items = p.get("rich_text", [])
        return "".join(t.get("plain_text", "") for t in items).strip()
    return ""

# ── Logica principale ─────────────────────────────────────────────────────────

def load_clients():
    pages = query_database(CLIENTS_DB_ID)
    clients = {}
    for p in pages:
        # Adatta "Nome" al nome reale della proprietà titolo nel tuo DB clienti
        name = prop(p, "Nome", "title") or prop(p, "Name", "title")
        clients[p["id"].replace("-", "")] = name
        clients[p["id"]] = name
    return clients

def load_deadlines(clients):
    today = date.today()
    filter_obj = {
        "and": [
            {"property": "Stato", "select": {"equals": "Attiva"}},
            {"property": "Data scadenza", "date": {"is_not_empty": True}},
        ]
    }
    pages = query_database(DEADLINES_DB_ID, filter_obj)
    items = []
    for p in pages:
        raw_date = prop(p, "Data scadenza", "date")
        if not raw_date:
            continue
        deadline = date.fromisoformat(raw_date[:10])
        days_left = (deadline - today).days
        if days_left < 0:
            continue  # già scaduta, salta

        tipo = prop(p, "TIpo", "select") or "Normativa"
        client_ids = prop(p, "Cliente", "relation")
        client_name = ""
        for cid in client_ids:
            c = clients.get(cid, "")
            if c:
                client_name = c
                break

        note = prop(p, "Note", "rich_text")

        items.append({
            "name":        prop(p, "Nome", "title") or prop(p, "Name", "title"),
            "tipo":        tipo,
            "cliente":     client_name,
            "deadline":    deadline,
            "days_left":   days_left,
            "note":        note,
            "notion_url":  p.get("url", ""),
        })

    items.sort(key=lambda x: x["days_left"])
    return items

MESI_IT = {1:"gennaio",2:"febbraio",3:"marzo",4:"aprile",5:"maggio",6:"giugno",
           7:"luglio",8:"agosto",9:"settembre",10:"ottobre",11:"novembre",12:"dicembre"}

def format_date_it(d):
    return f"{d.day} {MESI_IT[d.month]} {d.year}"

def urgency(days):
    if days <= 30:
        return "red", "Urgente"
    if days <= 90:
        return "amber", "Prossima"
    return "green", "Pianificata"

# ── Generazione HTML ──────────────────────────────────────────────────────────

def badge_html(tipo):
    cfg = TIPO_CONFIG.get(tipo, {"color": "blue", "icon": "📋"})
    col = cfg["color"]
    bg, border, text = COLOR_CSS.get(col, COLOR_CSS["blue"])
    return (
        f'<span style="background:#{bg};color:#{text};border:0.5px solid #{border};'
        f'font-size:10px;font-weight:500;padding:1px 7px;border-radius:99px;'
        f'display:inline-block;margin-left:6px;vertical-align:middle">'
        f'{cfg["icon"]} {tipo}</span>'
    )

def item_html(item):
    days = item["days_left"]
    color, _ = urgency(days)
    color_map = {"red": "#E24B4A", "amber": "#BA7517", "green": "#3B6D11"}
    hex_color = color_map[color]
    tipo = item["tipo"]
    cfg = TIPO_CONFIG.get(tipo, {"color": "blue", "icon": "📋"})
    col = cfg["color"]
    bg, border, _ = COLOR_CSS.get(col, COLOR_CSS["blue"])
    meta_parts = []
    if item["cliente"]:
        meta_parts.append(item["cliente"])
    if item["note"]:
        meta_parts.append(item["note"][:60] + ("…" if len(item["note"]) > 60 else ""))
    meta = " — ".join(meta_parts) if meta_parts else "&nbsp;"
    deadline_str = format_date_it(item["deadline"])
    url = item["notion_url"]
    link_open = f'<a href="{url}" target="_blank" style="text-decoration:none;color:inherit">' if url else "<div>"
    link_close = "</a>" if url else "</div>"

    return f"""
    <div data-tipo="{tipo}" style="margin-bottom:6px">
    {link_open}
    <div style="display:grid;grid-template-columns:1fr auto;align-items:center;gap:12px;
                padding:10px 12px;border-radius:8px;background:#f8f8f8;
                border:0.5px solid #e0e0e0;cursor:pointer">
      <div style="display:flex;align-items:center;gap:10px">
        <div style="width:32px;height:32px;border-radius:6px;display:flex;align-items:center;
                    justify-content:center;font-size:14px;flex-shrink:0;
                    background:#{bg};border:0.5px solid #{border}">
          {cfg['icon']}
        </div>
        <div>
          <div style="font-size:13px;font-weight:500;color:#1a1a1a;margin-bottom:2px">
            {item['name']}{badge_html(tipo)}
          </div>
          <div style="font-size:11px;color:#666">{meta}</div>
        </div>
      </div>
      <div style="text-align:right;flex-shrink:0">
        <div style="font-size:20px;font-weight:500;line-height:1;color:{hex_color}">{days}</div>
        <div style="font-size:10px;color:#888">giorni</div>
        <div style="font-size:11px;color:#666;margin-top:2px">{deadline_str}</div>
      </div>
    </div>
    {link_close}
    </div>"""

def section_html(label, dot_color, items):
    if not items:
        return ""
    dot_map = {"red": "#E24B4A", "amber": "#EF9F27", "green": "#639922"}
    dot_hex = dot_map.get(dot_color, "#888")
    items_html = "\n".join(item_html(i) for i in items)
    return f"""
    <div data-section="{dot_color}" style="margin-top:14px">
      <div style="font-size:11px;font-weight:500;color:#888;text-transform:uppercase;
                  letter-spacing:.05em;margin-bottom:8px;display:flex;align-items:center;gap:6px">
        <span style="width:6px;height:6px;border-radius:50%;background:{dot_hex};display:inline-block"></span>
        {label}
      </div>
      {items_html}
    </div>"""

def build_html(items):
    today = date.today()
    today_str = format_date_it(today)

    urgent  = [i for i in items if i["days_left"] <= 30]
    soon    = [i for i in items if 30 < i["days_left"] <= 90]
    planned = [i for i in items if i["days_left"] > 90]

    counts = {
        "urgent": len(urgent),
        "soon":   len(soon),
        "planned": len(planned),
        "total":   len(items),
    }

    all_tipos = sorted({i["tipo"] for i in items})
    filter_chips = '<div class="chip active" onclick="filter(\'tutte\',this)">Tutte</div>\n'
    for t in all_tipos:
        cfg = TIPO_CONFIG.get(t, {"icon": ""})
        filter_chips += f'<div class="chip" onclick="filter(\'{t}\',this)">{cfg["icon"]} {t}</div>\n'

    sections_html = (
        section_html("Urgenti — entro 30 giorni", "red", urgent) +
        section_html("Prossime — 30 a 90 giorni", "amber", soon) +
        section_html("Pianificate — oltre 90 giorni", "green", planned)
    )

    if not items:
        sections_html = '<p style="color:#888;font-size:13px;padding:12px 0">Nessuna scadenza attiva.</p>'

    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scadenze normative — Zeta Consulting</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f2f2f0; min-height: 100vh; }}
  .hero {{ background: #0f1c2e; padding: 20px 24px 16px; }}
  .hero h1 {{ font-size: 18px; font-weight: 500; color: #fff; margin-bottom: 2px; }}
  .hero .sub {{ font-size: 12px; color: #8fa8c8; }}
  .hero .date {{ font-size: 12px; color: #8fa8c8; }}
  .stats {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; margin-top: 16px; }}
  .stat {{ background: rgba(255,255,255,0.07); border-radius: 8px; padding: 10px 12px; }}
  .stat .n {{ font-size: 22px; font-weight: 500; color: #fff; line-height: 1; }}
  .stat .l {{ font-size: 11px; color: #8fa8c8; margin-top: 3px; }}
  .stat.red .n {{ color: #f09595; }}
  .stat.amber .n {{ color: #FAC775; }}
  .body {{ padding: 16px; max-width: 680px; margin: 0 auto; }}
  .filters {{ display: flex; gap: 6px; margin-bottom: 4px; flex-wrap: wrap; }}
  .chip {{ font-size: 12px; padding: 4px 12px; border-radius: 99px;
           border: 0.5px solid #ccc; background: #fff; color: #555;
           cursor: pointer; transition: all .15s; }}
  .chip.active {{ background: #0f1c2e; color: #fff; border-color: #0f1c2e; }}
  .footer {{ font-size: 11px; color: #aaa; text-align: center; padding: 16px 0; }}
  a:hover > div {{ border-color: #999 !important; }}
  @media (max-width: 480px) {{
    .stats {{ grid-template-columns: repeat(2,1fr); }}
    .hero {{ padding: 14px 16px 12px; }}
    .body {{ padding: 12px; }}
  }}
</style>
</head>
<body>

<div class="hero">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px">
    <div>
      <h1>Scadenze normative</h1>
      <div class="sub">Zeta Consulting S.r.l.</div>
    </div>
    <div class="date">{today_str}</div>
  </div>
  <div class="stats">
    <div class="stat red"><div class="n">{counts['urgent']}</div><div class="l">Urgenti &lt;30gg</div></div>
    <div class="stat amber"><div class="n">{counts['soon']}</div><div class="l">Prossime 30–90gg</div></div>
    <div class="stat"><div class="n">{counts['planned']}</div><div class="l">Pianificate</div></div>
    <div class="stat"><div class="n">{counts['total']}</div><div class="l">Totale attive</div></div>
  </div>
</div>

<div class="body">
  <div class="filters" style="margin-top:14px">
    {filter_chips}
  </div>
  <div id="content">
    {sections_html}
  </div>
  <div class="footer">Aggiornato il {generated_at} · Dati da Notion</div>
</div>

<script>
function filter(tipo, el) {{
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  document.querySelectorAll('[data-tipo]').forEach(item => {{
    item.style.display = (tipo === 'tutte' || item.dataset.tipo === tipo) ? '' : 'none';
  }});
  document.querySelectorAll('[data-section]').forEach(sec => {{
    const vis = [...sec.querySelectorAll('[data-tipo]')].some(i => i.style.display !== 'none');
    sec.style.display = vis ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("📡 Carico clienti da Notion...")
    clients = load_clients()
    print(f"   {len(clients)//2} clienti trovati")

    print("📅 Carico scadenze da Notion...")
    items = load_deadlines(clients)
    print(f"   {len(items)} scadenze attive")

    print("🔨 Genero index.html...")
    html = build_html(items)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ index.html generato con successo")

if __name__ == "__main__":
    main()