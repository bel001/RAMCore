"""
NoCode Studio - App de escritorio No-Code unificada (Windows / tkinter, solo stdlib)
Fusiona ideas de:
 - Plasmic      -> constructor visual drag & drop web (canvas + propiedades)
 - Saltcorn     -> tablas de datos + vistas (CRUD sin código)
 - flutter-builder (Sharifur) -> vista móvil + export Flutter
 - Appsmith     -> Queries REST/API + bindings {{...}}
 - Budibase     -> páginas, formularios CRUD, automatizaciones onClick

Uso:
  python nocode_studio.py
  No requiere pip. Guarda proyectos .nocode.json
"""
import json
import os
import re
import copy
import uuid
import urllib.request
import urllib.parse
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

APP_TITLE = "NoCode Studio"
BIND_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")

WIDGET_TYPES = [
    ("Etiqueta", "label"),
    ("Botón", "button"),
    ("Campo texto", "entry"),
    ("Área texto", "textarea"),
    ("Tabla", "table"),
    ("Lista", "list"),
    ("Imagen (URL)", "image"),
    ("Contenedor", "frame"),
    ("Título", "title"),
    ("Interruptor", "switch"),
]

def nid(prefix="w"):
    return f"{prefix}_{uuid.uuid4().hex[:6]}"

def default_widget(wtype, x=50, y=50):
    base = {"id": nid(), "type": wtype, "x": x, "y": y, "w": 160, "h": 40,
            "text": "Texto", "bg": "#ffffff", "fg": "#111111", "font_size": 10,
            "table": "", "src": "", "bind": "", "action": "nada",
            "action_msg": "¡Hola!", "action_page": "", "action_query": "",
            "action_table": "", "font_bold": False}
    if wtype == "title":
        base.update({"text": "Mi Título", "font_size": 18, "font_bold": True, "w": 260, "h": 45})
    elif wtype == "label":
        base.update({"text": "Etiqueta {{}}", "w": 180, "h": 30})
    elif wtype == "button":
        base.update({"text": "Clic aquí", "bg": "#4F46E5", "fg": "#ffffff", "w": 140, "h": 36,
                     "action": "mensaje", "action_msg": "¡Botón presionado!"})
    elif wtype == "entry":
        base.update({"text": "", "bind": "", "w": 180, "h": 30})
    elif wtype == "textarea":
        base.update({"text": "", "w": 220, "h": 80})
    elif wtype == "table":
        base.update({"text": "Tabla", "w": 340, "h": 160, "table": ""})
    elif wtype == "list":
        base.update({"text": "Item1;Item2;Item3", "w": 180, "h": 100})
    elif wtype == "image":
        base.update({"text": "[imagen]", "src": "", "w": 180, "h": 120, "bg": "#e5e7eb"})
    elif wtype == "frame":
        base.update({"text": "", "w": 300, "h": 160, "bg": "#f3f4f6"})
    elif wtype == "switch":
        base.update({"text": "ON/OFF", "w": 120, "h": 30})
    return base

def new_project(name="Mi App"):
    return {
        "app": "NoCodeStudio",
        "version": 1,
        "name": name,
        "theme": {"bg": "#ffffff"},
        "pages": [{"name": "Inicio", "bg": "#ffffff", "widgets": [
            default_widget("title", 40, 20),
            {**default_widget("label", 40, 70), "text": "Hola, construye sin código. Usa {{mi_tabla.nombre.0}} para enlazar datos."},
            {**default_widget("button", 40, 110)},
        ]}],
        "tables": {
            "mi_tabla": {"columns": [{"name": "nombre", "type": "texto"}, {"name": "edad", "type": "numero"}],
                         "rows": [{"nombre": "Ana", "edad": 28}, {"nombre": "Luis", "edad": 34}]}
        },
        "queries": [{"name": "mi_api", "method": "GET",
                     "url": "https://jsonplaceholder.typicode.com/todos/1",
                     "headers": "{}", "body": "", "last_result": ""}],
        "vars": {},
        "current_page": 0,
    }


class BindingEngine:
    """Resuelve {{tabla.campo.indice}} {{query.nombre}} {{var.nombre}} (estilo Appsmith)."""
    def __init__(self, project):
        self.p = project

    def resolve(self, text):
        if not isinstance(text, str) or "{{" not in text:
            return text
        def rep(m):
            expr = m.group(1).strip()
            try:
                return str(self.eval_expr(expr))
            except Exception:
                return m.group(0)
        return BIND_RE.sub(rep, text)

    def eval_expr(self, expr):
        parts = expr.split(".")
        if not parts or parts[0] == "":
            return ""
        # query.NOMBRE
        if parts[0] == "query" and len(parts) >= 2:
            for q in self.p.get("queries", []):
                if q["name"] == parts[1]:
                    data = q.get("last_result", "")
                    if len(parts) == 2:
                        return (data[:300] + "…") if len(str(data)) > 300 else data
                    # intentar JSON path simple query.mi_api.title
                    try:
                        j = json.loads(data) if isinstance(data, str) else data
                        cur = j
                        for k in parts[2:]:
                            if isinstance(cur, list):
                                cur = cur[int(k)]
                            elif isinstance(cur, dict):
                                cur = cur.get(k, "")
                            else:
                                return cur
                        return cur if not isinstance(cur, (dict, list)) else json.dumps(cur)[:300]
                    except Exception:
                        return data[:200]
            return ""
        # var.NOMBRE
        if parts[0] == "var" and len(parts) >= 2:
            return self.p.get("vars", {}).get(parts[1], "")
        # TABLA.campo.indice  ó TABLA (cuenta filas)
        tname = parts[0]
        tables = self.p.get("tables", {})
        if tname in tables:
            tbl = tables[tname]
            rows = tbl.get("rows", [])
            if len(parts) == 1:
                return f"{len(rows)} filas"
            col = parts[1]
            idx = 0
            if len(parts) >= 3:
                try:
                    idx = int(parts[2])
                except Exception:
                    idx = 0
            if 0 <= idx < len(rows):
                return rows[idx].get(col, "")
            return ""
        # atajo: tabla por defecto si expr = campo de primera tabla
        return ""


def run_query(q, timeout=12):
    method = q.get("method", "GET").upper()
    url = q.get("url", "")
    headers = {}
    try:
        headers = json.loads(q.get("headers") or "{}")
    except Exception:
        headers = {}
    data = None
    if method in ("POST", "PUT", "PATCH") and q.get("body"):
        data = q["body"].encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# ---------------- EXPORTS (Plasmic->HTML, flutter-builder->Dart) ----------------
def export_html(project, page_idx=0):
    eng = BindingEngine(project)
    page = project["pages"][page_idx]
    parts = [f"<h1>{project['name']} - {page['name']}</h1>"]
    for w in page["widgets"]:
        t = eng.resolve(w.get("text", ""))
        txt = (t or "").replace("<", "&lt;")
        style = f"position:absolute;left:{w['x']}px;top:{w['y']}px;width:{w['w']}px;height:{w['h']}px;background:{w.get('bg','#fff')};color:{w.get('fg','#111')};font-size:{w.get('font_size',12)}px;"
        wt = w["type"]
        if wt in ("title", "label"):
            tag = "h2" if wt == "title" else "div"
            parts.append(f'<{tag} style="{style}">{txt}</{tag}>')
        elif wt == "button":
            parts.append(f'<button style="{style}">{txt}</button>')
        elif wt == "entry":
            parts.append(f'<input value="{txt}" placeholder="{w.get("bind","")}" style="{style}"/>')
        elif wt == "textarea":
            parts.append(f'<textarea style="{style}">{txt}</textarea>')
        elif wt == "table":
            tbl = project["tables"].get(w.get("table",""), {"columns":[],"rows":[]})
            cols = "".join(f"<th>{c['name']}</th>" for c in tbl["columns"])
            rows = "".join("<tr>" + "".join(f"<td>{r.get(c['name'],'')}</td>" for c in tbl["columns"]) + "</tr>" for r in tbl["rows"])
            parts.append(f'<table border="1" style="{style}"><tr>{cols}</tr>{rows}</table>')
        elif wt == "list":
            items = "".join(f"<li>{i}</li>" for i in (w.get("text","").split(";")))
            parts.append(f'<ul style="{style}">{items}</ul>')
        elif wt in ("frame", "image", "switch"):
            parts.append(f'<div style="{style};border:1px solid #ccc">{txt or wt}</div>')
    queries_js = ""
    for q in project.get("queries", []):
        queries_js += f"// query {q['name']}: {q['method']} {q['url']}\n"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{project['name']}</title></head>
<body><div style="position:relative;width:900px;height:650px;margin:auto;border:1px solid #ddd">
{''.join(parts)}
</div><script>\n{queries_js}\n// Exportado desde NoCode Studio (fusión Plasmic+Saltcorn+Appsmith+Budibase+FlutterBuilder)\n</script></body></html>"""

def export_flutter(project, page_idx=0):
    page = project["pages"][page_idx]
    out = [f"// {project['name']} - {page['name']}  (generado por NoCode Studio, estilo flutter-builder)",
           "import 'package:flutter/material.dart';", "",
           f"class {re.sub(r'[^A-Za-z0-9]','',page['name']) or 'PageInicio'} extends StatelessWidget {{",
           "  const " + f"{re.sub(r'[^A-Za-z0-9]','',page['name']) or 'PageInicio'}" + "({super.key});",
           "  @override", "  Widget build(BuildContext context) {", "    return Scaffold(",
           f"      appBar: AppBar(title: const Text('{project['name']}')),",
           "      body: Stack(children: ["]
    for w in page["widgets"]:
        txt = w.get("text","").replace("'", "\\'")[:80]
        wt = w["type"]
        pos = f"Positioned(left:{w['x']}.0, top:{w['y']}.0, child: SizedBox(width:{w['w']}.0, height:{w['h']}.0, child: "
        if wt == "title":
            out.append(pos + f"Text('{txt}', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)))) ,")
        elif wt == "label":
            out.append(pos + f"Text('{txt}'))),")
        elif wt == "button":
            out.append(pos + f"ElevatedButton(onPressed: () {{}}, child: Text('{txt}')))),")
        elif wt in ("entry", "textarea"):
            out.append(pos + f"TextField(decoration: InputDecoration(hintText: '{txt}')))),")
        elif wt == "table":
            out.append(pos + f"Container(color: Colors.grey[200], child: Center(child: Text('Tabla: {w.get('table','')}'))))),")
        elif wt == "list":
            out.append(pos + f"ListView(children: const [Text('{txt}')]))),")
        else:
            out.append(pos + f"Container(color: Colors.grey[200], child: Text('{wt}')))),")
    out += ["      ]),", "    );", "  }", "}"]
    return "\n".join(out)


# ================= APP =================
class NoCodeStudio:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE + "  —  Plasmic+Saltcorn+Flutter+Appsmith+Budibase")
        self.root.geometry("1400x820")
        self.root.minsize(1120, 660)
        self.project = new_project()
        self.filepath = None
        self.selected_id = None
        self.mode = tk.StringVar(value="Web")  # Web (Plasmic) | Móvil (Flutter)
        self.live_vars = {}  # valores de entries en preview
        self._drag = None
        self.setup_theme()
        self.build_ui()
        self.refresh_all()

    # ---------- Tema premium oscuro (slate + acento azul) ----------
    def setup_theme(self):
        self.C = {
            "bg0": "#0b1220", "bg1": "#0f172a", "bg2": "#1e293b",
            "line": "#26334d", "tx": "#e2e8f0", "mut": "#94a3b8",
            "faint": "#64748b", "ac": "#38bdf8", "ac_hi": "#7dd3fc",
        }
        C = self.C
        self.root.configure(bg=C["bg1"])
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("TNotebook", background=C["bg1"], borderwidth=0)
        st.configure("TNotebook.Tab", background=C["bg1"], foreground=C["mut"],
                     padding=(12, 7), font=("Segoe UI", 9))
        st.map("TNotebook.Tab", background=[("selected", C["bg2"])],
               foreground=[("selected", "#ffffff")])
        st.configure("TFrame", background=C["bg1"])
        st.configure("Treeview", background="#0b1220", fieldbackground="#0b1220",
                     foreground=C["tx"], rowheight=24, borderwidth=0,
                     font=("Segoe UI", 9))
        st.configure("Treeview.Heading", background=C["bg2"], foreground="#ffffff",
                     font=("Segoe UI", 9, "bold"))
        st.map("Treeview", background=[("selected", C["ac"])],
               foreground=[("selected", "#0b1220")])
        st.configure("TCombobox", fieldbackground="#0b1220", background=C["bg2"],
                     foreground=C["tx"], arrowcolor=C["ac"])
        # Scrollbars modernas: delgadas, SIN flechas, mimetizadas con el escenario.
        # Se logra con un layout ttk propio (trough + thumb, sin botones).
        for orient, layout in (
            ("Vertical", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})]),
            ("Horizontal", [("Horizontal.Scrollbar.trough", {"sticky": "we", "children": [
                ("Horizontal.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})]),
        ):
            thin = f"Thin.{orient}.TScrollbar"
            st.layout(thin, layout)
            st.configure(thin, troughcolor="#0f172a", background="#334155",
                         bordercolor="#0f172a", lightcolor="#334155",
                         darkcolor="#334155", borderwidth=0, gripcount=0,
                         relief="flat", width=10)

    def mkbtn(self, parent, text, cmd, accent=False, **kw):
        """Botón oscuro con hover (reemplaza el gris plano de tkinter)."""
        base = "#38bdf8" if accent else "#1e293b"
        hov = "#7dd3fc" if accent else "#334155"
        b = tk.Button(parent, text=text, command=cmd, cursor="hand2",
                      relief="flat", bd=0, padx=12, pady=6,
                      font=("Segoe UI", 9, "bold" if accent else "normal"),
                      bg=base, fg="#0b1220" if accent else "#e2e8f0",
                      activebackground=hov,
                      activeforeground="#0b1220" if accent else "#ffffff", **kw)
        b.bind("<Enter>", lambda e: b.configure(bg=hov))
        b.bind("<Leave>", lambda e: b.configure(bg=base))
        return b

    def plabel(self, text):
        return tk.Label(self.prop_area, text=text, bg=self.C["bg1"],
                        fg=self.C["faint"], font=("Segoe UI", 8, "bold"))

    def pentry(self, initial=""):
        e = tk.Entry(self.prop_area, bg="#0b1220", fg="#e2e8f0",
                     insertbackground="#38bdf8", relief="flat",
                     highlightthickness=1, highlightbackground="#26334d",
                     highlightcolor="#38bdf8", font=("Segoe UI", 9))
        e.insert(0, initial)
        return e

    def _sync_stage(self):
        try:
            self.stage.configure(scrollregion=self.stage.bbox("all"))
        except Exception:
            pass

    # ---------- UI shell ----------
    def build_ui(self):
        top = tk.Frame(self.root, bg="#0b1220", height=56)
        top.pack(fill="x")
        top.pack_propagate(False)
        brand = tk.Frame(top, bg="#0b1220")
        brand.pack(side="left", padx=14)
        tk.Label(brand, text="NoCode Studio", fg="#ffffff", bg="#0b1220",
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        tk.Label(brand, text="v1.0  ·  Community Edition", fg="#38bdf8", bg="#0b1220",
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(8, 0))
        tk.Label(top, text="Plasmic · Saltcorn · Flutter Builder · Appsmith · Budibase",
                 fg="#64748b", bg="#0b1220", font=("Segoe UI", 8)).pack(side="left", padx=12)
        # Flat design: todos los botones iguales (#1e293b -> hover #334155).
        # El azul queda solo como acento sutil (marca + línea de 1px).
        for txt, cmd in [("Nuevo", self.cmd_new), ("Abrir", self.cmd_open),
                         ("Guardar", self.cmd_save), ("Vista previa", self.cmd_preview),
                         ("Export HTML", self.cmd_exp_html),
                         ("Export Flutter", self.cmd_exp_flutter)]:
            self.mkbtn(top, txt, cmd).pack(side="left", padx=3, pady=11)
        self.mkbtn(top, "Ayuda", self.show_help).pack(side="right", padx=12, pady=11)
        ttk.Combobox(top, textvariable=self.mode, values=["Web", "Móvil"],
                     width=7, state="readonly").pack(side="right", pady=16)
        tk.Frame(self.root, bg="#1e293b", height=1).pack(fill="x")

        main = tk.PanedWindow(self.root, orient="horizontal", sashwidth=6,
                                bg="#0b1220", bd=0)
        main.pack(fill="both", expand=True)

        # IZQUIERDA
        self.left_nb = ttk.Notebook(main)
        main.add(self.left_nb, minsize=300)
        self.tab_palette = tk.Frame(self.left_nb, bg="#0f172a")
        self.tab_pages = tk.Frame(self.left_nb, bg="#0f172a")
        self.tab_data = tk.Frame(self.left_nb, bg="#0f172a")
        self.tab_api = tk.Frame(self.left_nb, bg="#0f172a")
        self.tab_auto = tk.Frame(self.left_nb, bg="#0f172a")
        for t, n in [(self.tab_palette, "Paleta"), (self.tab_pages, "Páginas"),
                     (self.tab_data, "Datos"), (self.tab_api, "APIs"),
                     (self.tab_auto, "Lógica")]:
            self.left_nb.add(t, text=n)
        self.build_palette(); self.build_pages_tab(); self.build_data_tab(); self.build_api_tab(); self.build_auto_tab()

        # CENTRO
        center = tk.Frame(main, bg="#0f172a")
        main.add(center, minsize=560)
        toolbar = tk.Frame(center, bg="#0b1220", height=40)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        self.lbl_page = tk.Label(toolbar, text="Página: Inicio", bg="#0b1220", fg="#e2e8f0",
                                 font=("Segoe UI", 9, "bold"))
        self.lbl_page.pack(side="left", padx=12, pady=10)
        self.mkbtn(toolbar, "Duplicar", self.cmd_duplicate).pack(side="left", padx=2, pady=6)
        self.mkbtn(toolbar, "Eliminar", self.cmd_delete).pack(side="left", padx=2, pady=6)
        tk.Label(toolbar, text="Arrastra para mover · clic para seleccionar",
                 bg="#0b1220", fg="#64748b", font=("Segoe UI", 8)).pack(side="right", padx=12)
        wrap = tk.Frame(center, bg="#0f172a")
        wrap.pack(fill="both", expand=True)
        # Lienzo con scroll (estilo Figma): la hoja vive dentro y nunca se corta.
        self.stage = tk.Canvas(wrap, bg="#0f172a", highlightthickness=0)
        self.vbar = ttk.Scrollbar(wrap, orient="vertical", command=self.stage.yview,
                                    style="Thin.Vertical.TScrollbar")
        self.hbar = ttk.Scrollbar(wrap, orient="horizontal", command=self.stage.xview,
                                    style="Thin.Horizontal.TScrollbar")
        self.stage.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.vbar.pack(side="right", fill="y")
        self.hbar.pack(side="bottom", fill="x")
        self.stage.pack(side="left", fill="both", expand=True)
        self.canvas_frame = tk.Frame(self.stage, bg="#ffffff", highlightthickness=1,
                                     highlightbackground="#334155")
        self.stage.create_window(40, 40, window=self.canvas_frame, anchor="nw")
        self.canvas_frame.bind("<Button-1>", lambda e: self.select(None))
        self.canvas_frame.bind("<Configure>", lambda e: self._sync_stage())
        self.stage.bind("<MouseWheel>", lambda e: self.stage.yview_scroll(-1 if e.delta > 0 else 1, "units"))

        # DERECHA
        right = tk.Frame(main, bg="#0f172a", width=300)
        main.add(right, minsize=300)
        tk.Label(right, text="PROPIEDADES", bg="#0f172a", fg="#38bdf8",
                 font=("Segoe UI", 10, "bold")).pack(pady=(12, 0), anchor="w", padx=14)
        tk.Label(right, text="Panel de diseño visual", bg="#0f172a", fg="#64748b",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(0, 8))
        self.prop_area = tk.Frame(right, bg="#0f172a")
        self.prop_area.pack(fill="both", expand=True, padx=14)
        self.status = tk.Label(self.root, text="Listo", anchor="w", bg="#0b1220",
                               fg="#94a3b8", font=("Segoe UI", 8), padx=12, pady=4)
        self.status.pack(fill="x")

    # ---------- Paleta (Plasmic / flutter-builder) ----------
    def build_palette(self):
        tk.Label(self.tab_palette, text="PALETA DE COMPONENTES", bg="#0f172a",
                 fg="#64748b", font=("Segoe UI", 8, "bold")).pack(pady=(10, 2), anchor="w", padx=12)
        tk.Label(self.tab_palette, text="Clic para agregar al lienzo", bg="#0f172a",
                 fg="#e2e8f0", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(0, 6))
        for label, wtype in WIDGET_TYPES:
            self.mkbtn(self.tab_palette, f"+  {label}",
                       lambda t=wtype: self.add_widget(t),
                       anchor="w").pack(fill="x", padx=12, pady=4, ipady=6)
        tk.Label(self.tab_palette, text="Consejo: cambia a modo Móvil para\nprevisualizar ancho tipo Flutter (390px).",
                 bg="#0f172a", fg="#64748b", font=("Segoe UI", 8),
                 justify="left").pack(pady=12, padx=12, anchor="w")

    def build_pages_tab(self):
        self.pages_list = tk.Listbox(self.tab_pages, bg="#0b1220", fg="#e2e8f0",
                                     selectbackground="#38bdf8", selectforeground="#0b1220",
                                     relief="flat", highlightthickness=1,
                                     highlightbackground="#26334d",
                                     font=("Segoe UI", 9))
        self.pages_list.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        self.pages_list.bind("<<ListboxSelect>>", self.on_page_select)
        f = tk.Frame(self.tab_pages, bg="#0f172a")
        f.pack(fill="x", padx=10, pady=4)
        self.mkbtn(f, "Página", self.cmd_add_page).pack(side="left", expand=True, fill="x", padx=1)
        self.mkbtn(f, "Renombrar", self.cmd_rename_page).pack(side="left", expand=True, fill="x", padx=1)
        self.mkbtn(f, "Borrar", self.cmd_del_page).pack(side="left", expand=True, fill="x", padx=1)

    # ---------- Datos (Saltcorn / Budibase tables) ----------
    def build_data_tab(self):
        tk.Label(self.tab_data, text="TABLAS DE DATOS", bg="#0f172a",
                 fg="#64748b", font=("Segoe UI", 8, "bold")).pack(pady=(10, 2), anchor="w", padx=12)
        tk.Label(self.tab_data, text="Saltcorn + Budibase", bg="#0f172a",
                 fg="#e2e8f0", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(0, 6))
        f = tk.Frame(self.tab_data, bg="#0f172a")
        f.pack(fill="x", padx=10)
        self.tbl_combo = ttk.Combobox(f, state="readonly")
        self.tbl_combo.pack(side="left", expand=True, fill="x")
        self.tbl_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_grid())
        self.mkbtn(f, "+", self.cmd_add_table, width=3).pack(side="left", padx=(4, 0))
        self.mkbtn(f, "Col+", self.cmd_add_col, width=5).pack(side="left", padx=(4, 0))
        self.mkbtn(f, "Fila+", self.cmd_add_row, width=6).pack(side="left", padx=(4, 0))
        self.grid = ttk.Treeview(self.tab_data, show="headings")
        self.grid.pack(fill="both", expand=True, padx=10, pady=8)
        self.mkbtn(self.tab_data, "Eliminar fila seleccionada",
                   self.cmd_del_row).pack(padx=10, pady=2, fill="x")
        tk.Label(self.tab_data, text="Enlaza con {{tabla.campo.0}}  ·  Ej: {{mi_tabla.nombre.0}}",
                 bg="#0f172a", fg="#64748b", font=("Segoe UI", 8)).pack(pady=6)

    # ---------- APIs (Appsmith) ----------
    def build_api_tab(self):
        tk.Label(self.tab_api, text="CONSULTAS REST", bg="#0f172a",
                 fg="#64748b", font=("Segoe UI", 8, "bold")).pack(pady=(10, 2), anchor="w", padx=12)
        tk.Label(self.tab_api, text="Appsmith", bg="#0f172a",
                 fg="#e2e8f0", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(0, 6))
        self.api_list = tk.Listbox(self.tab_api, height=5, bg="#0b1220", fg="#e2e8f0",
                                   selectbackground="#38bdf8", selectforeground="#0b1220",
                                   relief="flat", highlightthickness=1,
                                   highlightbackground="#26334d", font=("Segoe UI", 9))
        self.api_list.pack(fill="x", padx=10)
        self.api_list.bind("<<ListboxSelect>>", self.on_query_select)
        f = tk.Frame(self.tab_api, bg="#0f172a")
        f.pack(fill="x", padx=10, pady=6)
        self.mkbtn(f, "+ Query", self.cmd_add_query).pack(side="left", expand=True, fill="x", padx=1)
        self.mkbtn(f, "Probar", self.cmd_test_query, accent=True).pack(side="left", expand=True, fill="x", padx=1)
        self.mkbtn(f, "X", self.cmd_del_query, width=4).pack(side="left", padx=1)
        self.q_name = tk.Entry(self.tab_api); self.q_method = ttk.Combobox(self.tab_api, values=["GET", "POST", "PUT", "DELETE"], width=8)
        self.q_url = tk.Entry(self.tab_api); self.q_body = tk.Text(self.tab_api, height=4)
        for w in (self.q_name, self.q_url):
            w.configure(bg="#0b1220", fg="#e2e8f0", insertbackground="#38bdf8",
                        relief="flat", highlightthickness=1,
                        highlightbackground="#26334d", highlightcolor="#38bdf8")
        self.q_body.configure(bg="#0b1220", fg="#e2e8f0", insertbackground="#38bdf8",
                              relief="flat", highlightthickness=1,
                              highlightbackground="#26334d", highlightcolor="#38bdf8",
                              font=("Consolas", 9))
        for lbl, w in [("Nombre:", self.q_name), ("Método:", self.q_method), ("URL:", self.q_url)]:
            tk.Label(self.tab_api, text=lbl, bg="#0f172a", fg="#64748b",
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12)
            w.pack(fill="x", padx=10, pady=2)
        tk.Label(self.tab_api, text="Body JSON (POST):", bg="#0f172a", fg="#64748b",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12)
        self.q_body.pack(fill="x", padx=10, pady=2)
        self.q_result = tk.Text(self.tab_api, height=7, bg="#0b1220", fg="#34d399", font=("Consolas", 8),
                                relief="flat", highlightthickness=1, highlightbackground="#26334d")
        self.q_result.pack(fill="both", expand=True, padx=10, pady=6)
        for w in (self.q_name, self.q_url):
            w.bind("<KeyRelease>", lambda e: self.save_query_fields())
        self.q_method.bind("<<ComboboxSelected>>", lambda e: self.save_query_fields())
        self.q_body.bind("<KeyRelease>", lambda e: self.save_query_fields())
        tk.Label(self.tab_api, text="Usa en textos: {{query.mi_api}} o {{query.mi_api.title}}",
                 bg="#0f172a", font=("Segoe UI", 8), fg="#64748b").pack(pady=(0, 8))

    # ---------- Lógica (Budibase automations) ----------
    def build_auto_tab(self):
        tk.Label(self.tab_auto, text="AUTOMATIZACIÓN", bg="#0f172a",
                 fg="#64748b", font=("Segoe UI", 8, "bold")).pack(pady=(10, 2), anchor="w", padx=12)
        tk.Label(self.tab_auto, text="Budibase", bg="#0f172a",
                 fg="#e2e8f0", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(0, 6))
        self.auto_info = tk.Label(self.tab_auto, text="Selecciona un Botón en el lienzo\npara configurar su acción onClick.",
                                  bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 8), justify="left")
        self.auto_info.pack(padx=12, pady=4, anchor="w")
        self.a_action = ttk.Combobox(self.tab_auto, state="readonly",
            values=["nada", "mensaje", "cambiar_pagina", "llamar_api", "insertar_fila", "set_var"])
        self.a_action.pack(fill="x", padx=10, pady=2)
        self.a_action.bind("<<ComboboxSelected>>", lambda e: self.save_auto())
        tk.Label(self.tab_auto, text="Mensaje / var(valor) / página / query / tabla:",
                 bg="#0f172a", fg="#64748b", font=("Segoe UI", 8)).pack(anchor="w", padx=12)
        self.a_msg = tk.Entry(self.tab_auto, bg="#0b1220", fg="#e2e8f0",
                              insertbackground="#38bdf8", relief="flat",
                              highlightthickness=1, highlightbackground="#26334d",
                              highlightcolor="#38bdf8")
        self.a_msg.pack(fill="x", padx=10, pady=2)
        self.a_msg.bind("<KeyRelease>", lambda e: self.save_auto())
        self.a_target = ttk.Combobox(self.tab_auto, state="readonly"); self.a_target.pack(fill="x", padx=10, pady=2)
        self.a_target.bind("<<ComboboxSelected>>", lambda e: self.save_auto())
        tk.Label(self.tab_auto, text="Variables globales ({{var.x}}):", bg="#0f172a",
                 fg="#64748b", font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(6, 0))
        self.var_text = tk.Text(self.tab_auto, height=5, bg="#0b1220", fg="#e2e8f0",
                                insertbackground="#38bdf8", relief="flat",
                                highlightthickness=1, highlightbackground="#26334d",
                                font=("Consolas", 9))
        self.var_text.pack(fill="x", padx=10, pady=2)
        self.mkbtn(self.tab_auto, "Guardar vars (JSON)",
                   self.cmd_save_vars).pack(padx=10, pady=6, fill="x")
        tk.Label(self.tab_auto, text="Acciones:\n· mensaje: popup\n· cambiar_pagina: navega\n· llamar_api: ejecuta query\n· insertar_fila: añade fila\n· set_var: clave=valor en Mensaje",
                 bg="#0f172a", font=("Segoe UI", 8), fg="#64748b", justify="left").pack(padx=12, anchor="w", pady=(0, 8))

    # ---------- helpers proyecto ----------
    def cur_page(self):
        return self.project["pages"][self.project["current_page"]]

    def get_widget(self, wid):
        for w in self.cur_page()["widgets"]:
            if w["id"] == wid:
                return w
        return None

    def set_status(self, t):
        self.status.config(text=t)

    # ---------- render lienzo ----------
    def refresh_all(self):
        self.refresh_pages_list(); self.render_canvas(); self.render_props()
        self.refresh_tables_combo(); self.refresh_grid(); self.refresh_queries(); self.refresh_auto()
        w = 390 if self.mode.get() == "Móvil" else 880
        self.canvas_frame.config(width=w, height=620)
        self.stage.update_idletasks()
        self._sync_stage()
        self.stage.xview_moveto(0)
        self.stage.yview_moveto(0)
        self.lbl_page.config(text=f"Página: {self.cur_page()['name']}  ({len(self.cur_page()['widgets'])} widgets)  |  Proyecto: {self.project['name']}")
        self.mode.trace_add if False else None

    def render_canvas(self):
        for c in list(self.canvas_frame.children.values()):
            c.destroy()
        eng = BindingEngine(self.project)
        page = self.cur_page()
        self.canvas_frame.config(bg=page.get("bg", "#ffffff"))
        for w in page["widgets"]:
            self.create_canvas_widget(w, eng, preview=False)
        # rastrear cambio de modo una sola vez
        try:
            self.mode.trace_vdelete("w", self._mode_tr)
        except Exception:
            pass
        self._mode_tr = self.mode.trace_add("write", lambda *a: self.refresh_all())

    def make_draggable(self, frame, w):
        def start(e):
            self.select(w["id"])
            self._drag = (e.x_root, e.y_root, w["x"], w["y"])
        def move(e):
            if not self._drag: return
            dx = e.x_root - self._drag[0]; dy = e.y_root - self._drag[1]
            w["x"] = max(0, self._drag[2] + dx); w["y"] = max(0, self._drag[3] + dy)
            frame.place(x=w["x"], y=w["y"])
        def stop(e):
            self._drag = None
            self.render_props()
        frame.bind("<Button-1>", start); frame.bind("<B1-Motion>", move); frame.bind("<ButtonRelease-1>", stop)

    def widget_border(self, w):
        return {"highlightthickness": 2, "highlightbackground": "#4F46E5" if w["id"] == self.selected_id else "#d1d5db"}

    def create_canvas_widget(self, w, eng, preview=False, parent=None):
        host = parent or self.canvas_frame
        wt = w["type"]
        bd = {} if preview else self.widget_border(w)
        box = tk.Frame(host, width=w["w"], height=w["h"], bg=w.get("bg", "#fff"), **bd)
        box.place(x=w["x"], y=w["y"])
        box.pack_propagate(False)
        txt = eng.resolve(w.get("text", ""))
        fg = w.get("fg", "#111")
        fs = int(w.get("font_size", 10))
        try:
            if wt == "title":
                tk.Label(box, text=txt, bg=w.get("bg","#fff"), fg=fg,
                         font=("Segoe UI", fs, "bold"), wraplength=w["w"]).pack(expand=True)
            elif wt == "label":
                tk.Label(box, text=txt, bg=w.get("bg","#fff"), fg=fg,
                         font=("Segoe UI", fs), wraplength=w["w"], justify="left").pack(expand=True, fill="both")
            elif wt == "button":
                b = tk.Button(box, text=txt, bg=w.get("bg","#4F46E5"), fg=fg, relief="flat",
                              command=lambda wid=w["id"]: self.fire_action(wid, preview))
                b.pack(expand=True, fill="both")
            elif wt == "entry":
                e = tk.Entry(box); e.insert(0, eng.resolve(w.get("bind","")) or txt); e.pack(expand=True, fill="both")
                if preview: self.live_vars[w["id"]] = e
            elif wt == "textarea":
                t = tk.Text(box, height=3); t.insert("1.0", txt); t.pack(expand=True, fill="both")
                if preview: self.live_vars[w["id"]] = t
            elif wt == "table":
                tbl = self.project["tables"].get(w.get("table",""), None)
                if tbl and tbl["columns"]:
                    cols = [c["name"] for c in tbl["columns"]]
                    tr = ttk.Treeview(box, columns=cols, show="headings", height=5)
                    for c in cols: tr.heading(c, text=c); tr.column(c, width=max(60, w["w"]//max(1,len(cols))-5))
                    for r in tbl["rows"][:50]: tr.insert("", "end", values=[r.get(c,"") for c in cols])
                    tr.pack(expand=True, fill="both")
                else:
                    tk.Label(box, text="Tabla: (elige en Propiedades)", fg="#888").pack(expand=True)
            elif wt == "list":
                lb = tk.Listbox(box)
                for it in (txt.split(";") if txt else ["(vacío)"]): lb.insert("end", it)
                lb.pack(expand=True, fill="both")
            elif wt == "image":
                tk.Label(box, text=f"[IMG] {w.get('src','')[:30] or txt}", bg="#e5e7eb",
                         wraplength=w["w"]).pack(expand=True, fill="both")
            elif wt == "frame":
                tk.Label(box, text=txt or "Contenedor", bg=w.get("bg","#f3f4f6"),
                         fg="#6b7280").pack(expand=True)
            elif wt == "switch":
                v = tk.BooleanVar(value=False)
                tk.Checkbutton(box, text=txt, variable=v, bg=w.get("bg","#fff")).pack(expand=True)
        except Exception as ex:
            tk.Label(box, text=f"ERR:{ex}").pack()
        if not preview:
            self.make_draggable(box, w)
            for child in box.winfo_children():
                child.bind("<Button-1>", lambda e, wid=w["id"]: (self.select(wid), "break"))
        return box

    # ---------- selección + propiedades ----------
    def select(self, wid):
        self.selected_id = wid
        self.render_canvas(); self.render_props(); self.refresh_auto()

    def render_props(self):
        for c in list(self.prop_area.children.values()):
            c.destroy()
        w = self.get_widget(self.selected_id) if self.selected_id else None
        if not w:
            tk.Label(self.prop_area, text="Nada seleccionado.\nClic en un widget del lienzo.",
                     bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 9),
                     justify="center").pack(pady=24)
            self.plabel("FONDO DE PÁGINA").pack(anchor="w", pady=(6, 2))
            bg = self.pentry(self.cur_page().get("bg", "#ffffff"))
            bg.pack(fill="x")
            bg.bind("<KeyRelease>", lambda e: (self.cur_page().__setitem__("bg", bg.get()), self.render_canvas()))
            return
        tk.Label(self.prop_area, text=f"{w['type'].upper()}  ·  {w['id']}", bg="#0f172a",
                 fg="#38bdf8", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(2, 8))
        rows = [("Texto (acepta {{...}})", "text"), ("Bind {{tabla.campo.i}}", "bind"),
                ("Ancho", "w"), ("Alto", "h"), ("X", "x"), ("Y", "y"),
                ("Color fondo", "bg"), ("Color texto", "fg"),
                ("Tamaño fuente", "font_size"), ("Imagen URL", "src")]
        self._entries = {}
        for lbl, key in rows:
            self.plabel(lbl.upper()).pack(anchor="w", pady=(6, 1))
            e = self.pentry(str(w.get(key, "")))
            e.pack(fill="x")
            e.bind("<KeyRelease>", lambda ev, k=key, ent=e: self.on_prop_change(k, ent.get()))
            self._entries[key] = e
        # tabla enlazada
        if w["type"] == "table":
            self.plabel("TABLA ENLAZADA").pack(anchor="w", pady=(6, 1))
            cb = ttk.Combobox(self.prop_area, values=list(self.project["tables"].keys()), state="readonly")
            cb.set(w.get("table", ""))
            cb.pack(fill="x")
            cb.bind("<<ComboboxSelected>>", lambda e: (w.__setitem__("table", cb.get()), self.render_canvas()))
        # lista items
        if w["type"] == "list":
            self.plabel("ITEMS SEPARADOS POR ;").pack(anchor="w", pady=(6, 1))

    def on_prop_change(self, key, val):
        w = self.get_widget(self.selected_id)
        if not w: return
        if key in ("w","h","x","y","font_size"):
            try: val = int(float(val))
            except Exception: return
        w[key] = val
        # re-render ligero: solo reposicionar si es geometría
        for child in self.canvas_frame.winfo_children():
            pass
        self.render_canvas_keep_focus(key)

    def render_canvas_keep_focus(self, changed_key):
        # re-render sin perder foco del entry que se edita
        focused = self.root.focus_get()
        self.render_canvas()
        if changed_key in getattr(self, "_entries", {}) and focused is not None:
            try:
                ent = self._entries[changed_key]
                ent.focus_set(); ent.icursor("end")
            except Exception:
                pass

    # ---------- páginas ----------
    def refresh_pages_list(self):
        self.pages_list.delete(0, "end")
        for i, p in enumerate(self.project["pages"]):
            self.pages_list.insert("end", f"{'▶ ' if i==self.project['current_page'] else ''}{p['name']}")

    def on_page_select(self, e):
        s = self.pages_list.curselection()
        if s:
            self.project["current_page"] = s[0]
            self.selected_id = None
            self.refresh_all()

    def cmd_add_page(self):
        name = simpledialog.askstring("Página", "Nombre:", initialvalue=f"Página {len(self.project['pages'])+1}")
        if name:
            self.project["pages"].append({"name": name, "bg": "#ffffff", "widgets": []})
            self.project["current_page"] = len(self.project["pages"]) - 1
            self.refresh_all()

    def cmd_rename_page(self):
        p = self.cur_page()
        n = simpledialog.askstring("Renombrar", "Nombre:", initialvalue=p["name"])
        if n: p["name"] = n; self.refresh_all()

    def cmd_del_page(self):
        if len(self.project["pages"]) <= 1:
            return messagebox.showwarning("Páginas", "Debe quedar al menos 1 página.")
        if messagebox.askyesno("Borrar", f"¿Borrar '{self.cur_page()['name']}'?"):
            del self.project["pages"][self.project["current_page"]]
            self.project["current_page"] = 0
            self.selected_id = None; self.refresh_all()

    # ---------- widgets ----------
    def add_widget(self, wtype):
        w = default_widget(wtype, x=60 + len(self.cur_page()["widgets"])*12, y=80 + len(self.cur_page()["widgets"])*12)
        if wtype == "table" and self.project["tables"]:
            w["table"] = list(self.project["tables"].keys())[0]
        self.cur_page()["widgets"].append(w)
        self.selected_id = w["id"]
        self.refresh_all()
        self.set_status(f"Agregado {wtype}")

    def cmd_duplicate(self):
        w = self.get_widget(self.selected_id)
        if not w: return
        c = copy.deepcopy(w); c["id"] = nid(); c["x"] += 20; c["y"] += 20
        self.cur_page()["widgets"].append(c); self.selected_id = c["id"]; self.refresh_all()

    def cmd_delete(self):
        if not self.selected_id: return
        self.cur_page()["widgets"] = [x for x in self.cur_page()["widgets"] if x["id"] != self.selected_id]
        self.selected_id = None; self.refresh_all()

    # ---------- datos ----------
    def refresh_tables_combo(self):
        names = list(self.project["tables"].keys())
        self.tbl_combo["values"] = names
        if names and self.tbl_combo.get() not in names:
            self.tbl_combo.set(names[0])
        # combos de automatización
        pages = [p["name"] for p in self.project["pages"]]
        queries = [q["name"] for q in self.project.get("queries", [])]
        tables = names
        cur = self.get_widget(self.selected_id)
        if cur:
            act = cur.get("action", "nada")
            if act == "cambiar_pagina": self.a_target["values"] = pages
            elif act == "llamar_api": self.a_target["values"] = queries
            elif act == "insertar_fila": self.a_target["values"] = tables
            else: self.a_target["values"] = []

    def cur_table_name(self):
        return self.tbl_combo.get() or (list(self.project["tables"].keys())[0] if self.project["tables"] else "")

    def refresh_grid(self):
        for c in self.grid.get_children(): self.grid.delete(c)
        tn = self.cur_table_name()
        if not tn or tn not in self.project["tables"]:
            self.grid["columns"] = []; return
        tbl = self.project["tables"][tn]
        cols = [c["name"] for c in tbl["columns"]]
        self.grid["columns"] = cols
        for c in cols: self.grid.heading(c, text=c); self.grid.column(c, width=110)
        for i, r in enumerate(tbl["rows"]):
            self.grid.insert("", "end", iid=str(i), values=[r.get(c, "") for c in cols])

    def cmd_add_table(self):
        n = simpledialog.askstring("Tabla", "Nombre tabla:", initialvalue="nueva_tabla")
        if n and n not in self.project["tables"]:
            self.project["tables"][n] = {"columns": [{"name": "campo1", "type": "texto"}], "rows": []}
            self.tbl_combo.set(n); self.refresh_tables_combo(); self.refresh_grid()

    def cmd_add_col(self):
        tn = self.cur_table_name()
        if not tn: return
        n = simpledialog.askstring("Columna", "Nombre columna:")
        if n:
            self.project["tables"][tn]["columns"].append({"name": n, "type": "texto"})
            self.refresh_grid()

    def cmd_add_row(self):
        tn = self.cur_table_name()
        if not tn: return
        tbl = self.project["tables"][tn]
        row = {}
        for c in tbl["columns"]:
            v = simpledialog.askstring("Fila", f"{c['name']}:", initialvalue="")
            if v is None: return
            row[c["name"]] = v
        tbl["rows"].append(row); self.refresh_grid(); self.render_canvas()

    def cmd_del_row(self):
        tn = self.cur_table_name()
        s = self.grid.selection()
        if not tn or not s: return
        del self.project["tables"][tn]["rows"][int(s[0])]
        self.refresh_grid(); self.render_canvas()

    # ---------- queries ----------
    def refresh_queries(self):
        self.api_list.delete(0, "end")
        for q in self.project.get("queries", []):
            self.api_list.insert("end", f"{q['method']} {q['name']}")
        if self.project.get("queries"):
            self.api_list.selection_set(0)
            self.show_query(self.project["queries"][0])
        else:
            for w in (self.q_name, self.q_url): w.delete(0, "end")
            self.q_result.delete("1.0", "end")

    def on_query_select(self, e):
        s = self.api_list.curselection()
        if s: self.show_query(self.project["queries"][s[0]])

    def show_query(self, q):
        self.q_name.delete(0, "end"); self.q_name.insert(0, q["name"])
        self.q_method.set(q.get("method", "GET"))
        self.q_url.delete(0, "end"); self.q_url.insert(0, q.get("url", ""))
        self.q_body.delete("1.0", "end"); self.q_body.insert("1.0", q.get("body", ""))
        self.q_result.delete("1.0", "end"); self.q_result.insert("1.0", (q.get("last_result") or "")[:4000])

    def cur_query(self):
        s = self.api_list.curselection()
        if not s or not self.project.get("queries"): return None
        return self.project["queries"][s[0]]

    def save_query_fields(self):
        q = self.cur_query()
        if not q: return
        q["name"] = self.q_name.get().strip() or q["name"]
        q["method"] = self.q_method.get() or "GET"
        q["url"] = self.q_url.get().strip()
        q["body"] = self.q_body.get("1.0", "end").strip()
        # refrescar nombres sin perder selección
        s = self.api_list.curselection()
        self.api_list.delete(0, "end")
        for qq in self.project["queries"]:
            self.api_list.insert("end", f"{qq['method']} {qq['name']}")
        if s: self.api_list.selection_set(s)

    def cmd_add_query(self):
        self.project.setdefault("queries", []).append(
            {"name": f"api_{len(self.project['queries'])+1}", "method": "GET",
             "url": "https://jsonplaceholder.typicode.com/todos/1", "headers": "{}", "body": "", "last_result": ""})
        self.refresh_queries()

    def cmd_del_query(self):
        q = self.cur_query()
        if q:
            self.project["queries"].remove(q); self.refresh_queries()

    def cmd_test_query(self):
        q = self.cur_query()
        if not q: return
        self.save_query_fields()
        try:
            self.set_status(f"Llamando {q['method']} {q['url']}…")
            self.root.update()
            data = run_query(q)
            q["last_result"] = data
            self.show_query(q)
            self.set_status(f"OK: {len(data)} bytes. Usa {{{{query.{q['name']}}}}}")
            self.render_canvas()
        except Exception as ex:
            messagebox.showerror("Query", str(ex))

    # ---------- automatizaciones ----------
    def refresh_auto(self):
        w = self.get_widget(self.selected_id) if self.selected_id else None
        if not w:
            self.auto_info.config(text="Selecciona un Botón en el lienzo\npara configurar su acción onClick.")
            return
        self.auto_info.config(text=f"Widget: {w['type']}  {w['id']}\nTexto: {(w.get('text') or '')[:40]}")
        self.a_action.set(w.get("action", "nada"))
        # msg / target según acción
        act = w.get("action", "nada")
        if act == "set_var": self.a_msg.delete(0,"end"); self.a_msg.insert(0, w.get("action_msg","clave=valor"))
        elif act == "mensaje": self.a_msg.delete(0,"end"); self.a_msg.insert(0, w.get("action_msg",""))
        else: self.a_msg.delete(0,"end"); self.a_msg.insert(0, w.get("action_msg",""))
        pages = [p["name"] for p in self.project["pages"]]
        queries = [q["name"] for q in self.project.get("queries", [])]
        tables = list(self.project["tables"].keys())
        if act == "cambiar_pagina":
            self.a_target["values"] = pages; self.a_target.set(w.get("action_page",""))
        elif act == "llamar_api":
            self.a_target["values"] = queries; self.a_target.set(w.get("action_query",""))
        elif act == "insertar_fila":
            self.a_target["values"] = tables; self.a_target.set(w.get("action_table",""))
        else:
            self.a_target["values"] = []; self.a_target.set("")
        try:
            self.var_text.delete("1.0","end")
            self.var_text.insert("1.0", json.dumps(self.project.get("vars",{}), indent=2, ensure_ascii=False))
        except Exception:
            pass

    def save_auto(self):
        w = self.get_widget(self.selected_id)
        if not w: return
        w["action"] = self.a_action.get()
        w["action_msg"] = self.a_msg.get()
        tgt = self.a_target.get()
        w["action_page"] = tgt; w["action_query"] = tgt; w["action_table"] = tgt

    def cmd_save_vars(self):
        try:
            self.project["vars"] = json.loads(self.var_text.get("1.0","end") or "{}")
            self.set_status("Vars guardadas")
            self.render_canvas()
        except Exception as ex:
            messagebox.showerror("Vars", f"JSON inválido: {ex}")

    def fire_action(self, wid, is_preview):
        # busca en página actual o en preview
        w = None
        for ww in self.cur_page()["widgets"]:
            if ww["id"] == wid: w = ww; break
        if not w: return
        eng = BindingEngine(self.project)
        act = w.get("action", "nada")
        msg = eng.resolve(w.get("action_msg", ""))
        if act == "mensaje":
            messagebox.showinfo(self.project["name"], msg or eng.resolve(w.get("text","")))
        elif act == "cambiar_pagina":
            for i, p in enumerate(self.project["pages"]):
                if p["name"] == w.get("action_page"):
                    self.project["current_page"] = i
                    self.selected_id = None
                    self.refresh_all()
                    if is_preview: self.cmd_preview()
                    return
            messagebox.showwarning("Navegación", "Página destino no encontrada.")
        elif act == "llamar_api":
            q = next((x for x in self.project.get("queries",[]) if x["name"]==w.get("action_query")), None)
            if not q: return messagebox.showwarning("API", "Query no encontrada.")
            try:
                q["last_result"] = run_query(q)
                messagebox.showinfo("API", f"OK {q['name']}: {len(q['last_result'])} bytes")
                self.refresh_queries(); self.render_canvas()
                if is_preview: self.cmd_preview()
            except Exception as ex:
                messagebox.showerror("API", str(ex))
        elif act == "insertar_fila":
            tn = w.get("action_table")
            if tn in self.project["tables"]:
                tbl = self.project["tables"][tn]
                # usa entries visibles del preview si existen, si no usa texto del botón
                row = {}
                for c in tbl["columns"]:
                    row[c["name"]] = msg or f"nuevo_{len(tbl['rows'])+1}"
                tbl["rows"].append(row)
                self.refresh_grid(); self.render_canvas()
                messagebox.showinfo("Datos", f"Fila insertada en {tn}")
                if is_preview: self.cmd_preview()
        elif act == "set_var":
            # formato clave=valor
            if "=" in (w.get("action_msg","")):
                k, v = w.get("action_msg","").split("=",1)
                self.project["vars"][k.strip()] = eng.resolve(v.strip())
                self.refresh_auto(); self.render_canvas()
                if is_preview: self.cmd_preview()

    # ---------- preview / run ----------
    def cmd_preview(self):
        eng = BindingEngine(self.project)
        win = tk.Toplevel(self.root)
        win.title(f"▶ {self.project['name']} — {self.cur_page()['name']}  (vista funcional)")
        wdt = 420 if self.mode.get() == "Móvil" else 900
        win.geometry(f"{wdt}x660")
        canvas = tk.Frame(win, bg=self.cur_page().get("bg","#fff"))
        canvas.pack(fill="both", expand=True)
        self.live_vars = {}
        # copiar widgets para que el preview tenga sus propios ids pero mismas acciones
        for w in self.cur_page()["widgets"]:
            self.create_canvas_widget(w, eng, preview=True, parent=canvas)
        tk.Label(win, text="Vista previa funcional: bindings {{...}} y acciones onClick activos.",
                 bg="#111827", fg="#9ca3af", font=("Segoe UI", 8)).pack(fill="x")

    # ---------- archivo ----------
    def cmd_new(self):
        if messagebox.askyesno("Nuevo", "¿Descartar proyecto actual?"):
            self.project = new_project(); self.filepath=None; self.selected_id=None; self.refresh_all()

    def cmd_open(self):
        p = filedialog.askopenfilename(filetypes=[("NoCode JSON","*.nocode.json"),("JSON","*.json")])
        if not p: return
        try:
            with open(p, "r", encoding="utf-8") as f:
                self.project = json.load(f)
            self.filepath = p; self.selected_id=None; self.refresh_all()
            self.set_status(f"Abierto {p}")
        except Exception as ex:
            messagebox.showerror("Abrir", str(ex))

    def cmd_save(self):
        p = self.filepath or filedialog.asksaveasfilename(defaultextension=".nocode.json",
                    filetypes=[("NoCode JSON","*.nocode.json")])
        if not p: return
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.project, f, indent=2, ensure_ascii=False)
            self.filepath = p; self.set_status(f"Guardado {p}")
        except Exception as ex:
            messagebox.showerror("Guardar", str(ex))

    def cmd_exp_html(self):
        p = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML","*.html")])
        if not p: return
        with open(p, "w", encoding="utf-8") as f:
            f.write(export_html(self.project, self.project["current_page"]))
        messagebox.showinfo("Export", f"HTML guardado:\n{p}")

    def cmd_exp_flutter(self):
        p = filedialog.asksaveasfilename(defaultextension=".dart", filetypes=[("Dart","*.dart")])
        if not p: return
        with open(p, "w", encoding="utf-8") as f:
            f.write(export_flutter(self.project, self.project["current_page"]))
        messagebox.showinfo("Export", f"Flutter guardado:\n{p}\n\nPégalo en lib/ de tu proyecto Flutter.")

    def show_help(self):
        messagebox.showinfo("Bindings {{...}}",
            "En cualquier Texto puedes usar:\n\n"
            "· {{mi_tabla.nombre.0}}  → fila 0, columna nombre\n"
            "· {{mi_tabla}}  → cuenta filas\n"
            "· {{query.mi_api}}  → último resultado API\n"
            "· {{query.mi_api.title}}  → campo JSON\n"
            "· {{var.mi_var}}  → variable global (pestaña Lógica)\n\n"
            "Origen:\n· Tablas = Saltcorn/Budibase\n· Queries = Appsmith\n"
            "· Lienzo = Plasmic · Móvil/Export = flutter-builder")


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "clam" in style.theme_names(): style.theme_use("clam")
    except Exception:
        pass
    NoCodeStudio(root)
    root.mainloop()

if __name__ == "__main__":
    main()
