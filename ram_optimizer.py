"""
RAMCore - Optimizador de memoria RAM avanzado para Windows estilo RAMMap
- Vaciado de Working Sets (EmptyWorkingSet + SetProcessWorkingSetSize Trim)
- Purga de Standby List y Caché de Archivos del Sistema con privilegios NT reales
- Monitor de procesos con mayor consumo de RAM en tiempo real
- Lista de exclusión de procesos protegidos (Whitelist)
- Minimización a la Bandeja del Sistema (System Tray con pystray)
- Persistencia de configuración en config.json
- Elevación de privilegios UAC (Ejecutar como Administrador)
"""
import ctypes
from ctypes import wintypes
import gc
import json
import os
import sys
import threading
import time
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

try:
    import psutil
except ImportError:
    raise SystemExit("Falta psutil. Instala con: pip install psutil")

try:
    from PIL import Image
    import pystray
    HAVE_PYSTRAY = True
except ImportError:
    HAVE_PYSTRAY = False

# ---------- Rutas seguras (PyInstaller compatible) ----------
def get_app_dir():
    """Directorio persistente donde reside el script o el .exe (para config.json)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(filename):
    """Directorio para recursos empaquetados (iconos, imágenes)."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

CONFIG_PATH = os.path.join(get_app_dir(), "config.json")

# ---------- Configuración por defecto ----------
DEFAULT_CONFIG = {
    "umbral": 75,
    "intervalo": 60,
    "auto_opt": False,
    "minimize_to_tray": True,
    "whitelist": ["explorer.exe", "dwm.exe", "searchhost.exe"]
}

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(data)
                return config
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error guardando config: {e}")

# ---------- Privilegios NT y Windows API ----------
kernel32 = ctypes.windll.kernel32
advapi32 = ctypes.windll.advapi32
shell32 = ctypes.windll.shell32
psapi = ctypes.windll.psapi if hasattr(ctypes.windll, "psapi") else kernel32

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_SET_QUOTA = 0x0100
TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY = 0x0008
SE_PRIVILEGE_ENABLED = 0x00000002

class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

class LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

class TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [("PrivilegeCount", wintypes.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]

def is_admin():
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False

def restart_as_admin():
    """Relanza la aplicación solicitando elevación UAC."""
    try:
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        if getattr(sys, "frozen", False):
            shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        else:
            shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
        sys.exit(0)
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo elevar privilegios: {e}")

def enable_privilege(privilege_name):
    """Habilita un privilegio específico en el token del proceso actual."""
    try:
        hToken = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, ctypes.byref(hToken)):
            return False
        luid = LUID()
        if not advapi32.LookupPrivilegeValueW(None, privilege_name, ctypes.byref(luid)):
            kernel32.CloseHandle(hToken)
            return False
        tp = TOKEN_PRIVILEGES()
        tp.PrivilegeCount = 1
        tp.Privileges[0].Luid = luid
        tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
        res = advapi32.AdjustTokenPrivileges(hToken, False, ctypes.byref(tp), ctypes.sizeof(tp), None, None)
        err = kernel32.GetLastError()
        kernel32.CloseHandle(hToken)
        return res != 0 and err == 0
    except Exception:
        return False

def init_nt_privileges():
    """Activa privilegios esenciales para purga de Standby List y Caché de Archivos."""
    if is_admin():
        enable_privilege("SeIncreaseQuotaPrivilege")
        enable_privilege("SeProfileSingleProcessPrivilege")

init_nt_privileges()

# ---------- Limpieza de Memoria ----------
def empty_working_sets(whitelist=None):
    """Vacía el Working Set de los procesos excepto los incluidos en la whitelist."""
    if whitelist is None:
        whitelist = set()
    else:
        whitelist = {w.lower().strip() for w in whitelist}

    count_ok = 0
    count_fail = 0
    count_skipped = 0

    for proc in psutil.process_iter(["pid", "name"]):
        pname = (proc.info.get("name") or "").lower()
        if pname in whitelist:
            count_skipped += 1
            continue

        pid = proc.info.get("pid")
        if not pid or pid <= 4:
            continue

        try:
            h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, pid)
            if not h:
                count_fail += 1
                continue
            try:
                # 1) EmptyWorkingSet
                try:
                    kernel32.EmptyWorkingSet(h)
                except Exception:
                    pass
                # 2) Trim Working Set
                try:
                    kernel32.SetProcessWorkingSetSize(h, ctypes.c_size_t(-1), ctypes.c_size_t(-1))
                except Exception:
                    pass
                count_ok += 1
            finally:
                kernel32.CloseHandle(h)
        except Exception:
            count_fail += 1

    return count_ok, count_fail, count_skipped

def empty_single_process(pid):
    """Vacía el working set de un proceso específico."""
    try:
        h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, pid)
        if not h:
            return False
        try:
            kernel32.EmptyWorkingSet(h)
            kernel32.SetProcessWorkingSetSize(h, ctypes.c_size_t(-1), ctypes.c_size_t(-1))
            return True
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        return False

def clear_system_file_cache():
    """Vacía caché de archivos del sistema."""
    try:
        res = kernel32.SetSystemFileCacheSize(ctypes.c_size_t(-1), ctypes.c_size_t(-1), 0)
        return bool(res)
    except Exception:
        return False

def purge_standby_list():
    """Purga la Standby List vía NtSetSystemInformation."""
    try:
        ntdll = ctypes.windll.ntdll
        class SYSTEM_MEMORY_LIST_COMMAND(ctypes.Structure):
            _fields_ = [("Command", ctypes.c_int)]
        cmd = SYSTEM_MEMORY_LIST_COMMAND(4)  # MemoryPurgeStandbyList = 4
        status = ntdll.NtSetSystemInformation(80, ctypes.byref(cmd), ctypes.sizeof(cmd))
        return status == 0
    except Exception:
        return False

def get_top_ram_processes(limit=15):
    """Obtiene los procesos ordenados por uso de memoria RAM (RSS)."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            mem = p.info["memory_info"].rss / 1024 / 1024
            procs.append({
                "pid": p.info["pid"],
                "name": p.info["name"] or f"PID {p.info['pid']}",
                "ram_mb": mem
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    procs.sort(key=lambda x: x["ram_mb"], reverse=True)
    return procs[:limit]

# ---------- Interfaz Gráfica (Tkinter) ----------
class RAMOptimizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RAMCore - Windows Memory Optimizer")
        self.root.geometry("520x680")
        self.root.minsize(480, 600)

        self.cfg = load_config()

        # Paleta moderna oscura
        self.bg = "#181825"
        self.card = "#1e1e2e"
        self.surface = "#313244"
        self.accent = "#00d4a4"
        self.texto = "#cdd6f4"
        self.subtext = "#a6adc8"
        self.warn = "#f38ba8"
        self.root.configure(bg=self.bg)

        # Icono de ventana
        self.ico_path = get_resource_path("icono.ico")
        self.png_path = get_resource_path("icono.png")
        if os.path.exists(self.ico_path):
            try:
                self.root.iconbitmap(self.ico_path)
            except Exception:
                pass

        # Configurar estilos ttk
        self.setup_styles()

        # Cabecera
        self.build_header()

        # Pestañas (Notebook)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=(5, 10))

        # Pestaña 1: Optimización
        self.tab_opt = tk.Frame(self.notebook, bg=self.bg)
        self.notebook.add(self.tab_opt, text=" ⚡ Optimización ")
        self.build_tab_optimization()

        # Pestaña 2: Monitor Top Procesos
        self.tab_proc = tk.Frame(self.notebook, bg=self.bg)
        self.notebook.add(self.tab_proc, text=" 📊 Top Procesos ")
        self.build_tab_processes()

        # Pestaña 3: Configuración y Exclusiones
        self.tab_cfg = tk.Frame(self.notebook, bg=self.bg)
        self.notebook.add(self.tab_cfg, text=" ⚙️ Ajustes & Exclusiones ")
        self.build_tab_settings()

        # Variables de estado
        self.total_liberado = 0.0
        self.optimizando = False
        self.ultima_auto = 0
        self.tray_icon = None

        # Configurar Minimización a la Bandeja
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)
        if HAVE_PYSTRAY:
            self.init_tray_icon()

        self.log_msg("RAMCore iniciado correctamente.")
        if is_admin():
            self.log_msg("🛡️ Privilegios de Administrador detectados (Limpieza profunda activa).")
        else:
            self.log_msg("ℹ️ Ejecutándose sin permisos de Admin (Purga Standby/Caché omitida).")

        # Bucle de actualización
        self.actualizar_ui()
        self.actualizar_top_procesos()

    def setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TNotebook", background=self.bg, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.card, foreground=self.subtext,
                        padding=[14, 7], font=("Segoe UI", 9, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", self.accent)],
                  foreground=[("selected", "#11111b")])

        style.configure("TProgressbar", background=self.accent, troughcolor=self.surface,
                        borderwidth=0, thickness=14)

        style.configure("Treeview", background="#11111b", foreground=self.texto,
                        fieldbackground="#11111b", rowheight=24, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background=self.surface, foreground=self.accent,
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", self.surface)],
                  foreground=[("selected", self.accent)])

    def build_header(self):
        top_frame = tk.Frame(self.root, bg=self.bg)
        top_frame.pack(fill="x", padx=16, pady=(12, 4))

        tk.Label(top_frame, text="⚡ RAMCORE", font=("Segoe UI", 18, "bold"),
                 bg=self.bg, fg=self.accent).pack(side="left")

        # Badge Admin
        if is_admin():
            lbl_badge = tk.Label(top_frame, text="🛡️ ADMIN ACTIVO", font=("Segoe UI", 8, "bold"),
                                 bg="#2e4c38", fg="#a6e3a1", padx=8, pady=3)
            lbl_badge.pack(side="right")
        else:
            btn_admin = tk.Button(top_frame, text="🛡️ Elevar a Admin", font=("Segoe UI", 8, "bold"),
                                  bg="#45382b", fg="#fab387", activebackground="#fab387",
                                  relief="flat", cursor="hand2", command=restart_as_admin)
            btn_admin.pack(side="right")

    # ---------- PESTAÑA 1: OPTIMIZACIÓN ----------
    def build_tab_optimization(self):
        # Tarjeta métricas
        frame = tk.Frame(self.tab_opt, bg=self.card, padx=16, pady=12)
        frame.pack(fill="x", padx=10, pady=(10, 8))

        self.lbl_porcentaje = tk.Label(frame, text="--%", font=("Segoe UI", 32, "bold"),
                                       bg=self.card, fg=self.texto)
        self.lbl_porcentaje.pack()

        self.barra = ttk.Progressbar(frame, mode="determinate", style="TProgressbar")
        self.barra.pack(fill="x", pady=6)

        self.lbl_detalle = tk.Label(frame, text="Cargando métricas...", font=("Segoe UI", 9),
                                    bg=self.card, fg=self.subtext)
        self.lbl_detalle.pack()

        self.lbl_liberado = tk.Label(frame, text="Total liberado esta sesión: 0 MB",
                                     font=("Segoe UI", 9, "bold"), bg=self.card, fg=self.accent)
        self.lbl_liberado.pack(pady=(4, 0))

        # Botón Optimizar
        btn_frame = tk.Frame(self.tab_opt, bg=self.bg)
        btn_frame.pack(pady=6)

        self.btn_optimizar = tk.Button(btn_frame, text="🧹 OPTIMIZAR AHORA", font=("Segoe UI", 11, "bold"),
                                       bg=self.accent, fg="#11111b", width=24, height=2,
                                       relief="flat", cursor="hand2", command=self.on_optimizar)
        self.btn_optimizar.pack()

        # Tarjeta Modo Automático
        auto_frame = tk.Frame(self.tab_opt, bg=self.card, padx=16, pady=10)
        auto_frame.pack(fill="x", padx=10, pady=4)

        self.auto_var = tk.BooleanVar(value=self.cfg.get("auto_opt", False))
        self.chk_auto = tk.Checkbutton(auto_frame, text="Modo Automático en Segundo Plano",
                                       variable=self.auto_var, bg=self.card, fg=self.texto,
                                       selectcolor=self.surface, activebackground=self.card,
                                       font=("Segoe UI", 9, "bold"), command=self.on_toggle_auto)
        self.chk_auto.pack(anchor="w")

        umbral_box = tk.Frame(auto_frame, bg=self.card)
        umbral_box.pack(fill="x", pady=(6, 2))
        tk.Label(umbral_box, text="Disparar si la RAM supera:", bg=self.card, fg=self.subtext,
                 font=("Segoe UI", 9)).pack(side="left")

        self.lbl_umbral = tk.Label(umbral_box, text=f"{self.cfg.get('umbral', 75)}%", bg=self.card,
                                   fg=self.accent, font=("Segoe UI", 9, "bold"))
        self.lbl_umbral.pack(side="right")

        self.umbral_var = tk.IntVar(value=self.cfg.get("umbral", 75))
        self.scale = tk.Scale(auto_frame, from_=50, to=95, orient="horizontal",
                              variable=self.umbral_var, bg=self.card, fg=self.texto,
                              highlightthickness=0, command=self.on_scale_change)
        self.scale.pack(fill="x")

        int_frame = tk.Frame(auto_frame, bg=self.card)
        int_frame.pack(fill="x", pady=(4, 0))
        tk.Label(int_frame, text="Revisar cada (segundos):", bg=self.card, fg=self.subtext,
                 font=("Segoe UI", 9)).pack(side="left")

        self.intervalo_var = tk.IntVar(value=self.cfg.get("intervalo", 60))
        self.spin_intervalo = tk.Spinbox(int_frame, from_=15, to=600, textvariable=self.intervalo_var,
                                         width=6, font=("Segoe UI", 9), command=self.save_current_settings)
        self.spin_intervalo.pack(side="right")

        # Registro de logs
        tk.Label(self.tab_opt, text="Registro de Actividad:", bg=self.bg, fg=self.subtext,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=(6, 2))

        self.log = tk.Text(self.tab_opt, height=7, bg="#11111b", fg=self.accent,
                           font=("Consolas", 8), relief="flat", state="disabled")
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 8))

    # ---------- PESTAÑA 2: TOP PROCESOS ----------
    def build_tab_processes(self):
        top_bar = tk.Frame(self.tab_proc, bg=self.bg)
        top_bar.pack(fill="x", padx=10, pady=(10, 6))

        tk.Label(top_bar, text="Procesos con mayor consumo de memoria:", bg=self.bg, fg=self.texto,
                 font=("Segoe UI", 9, "bold")).pack(side="left")

        btn_refresh = tk.Button(top_bar, text="🔄 Actualizar", font=("Segoe UI", 8, "bold"),
                                bg=self.surface, fg=self.texto, relief="flat", cursor="hand2",
                                command=self.actualizar_top_procesos)
        btn_refresh.pack(side="right")

        # Treeview
        columns = ("pid", "name", "ram")
        self.tree = ttk.Treeview(self.tab_proc, columns=columns, show="headings", height=12)
        self.tree.heading("pid", text="PID")
        self.tree.heading("name", text="Nombre del Proceso")
        self.tree.heading("ram", text="Memoria RAM (MB)")

        self.tree.column("pid", width=70, anchor="center")
        self.tree.column("name", width=230, anchor="w")
        self.tree.column("ram", width=120, anchor="e")
        self.tree.pack(fill="both", expand=True, padx=10, pady=4)

        # Acciones de procesos
        act_frame = tk.Frame(self.tab_proc, bg=self.bg)
        act_frame.pack(fill="x", padx=10, pady=(6, 10))

        btn_trim_proc = tk.Button(act_frame, text="🧹 Vaciar este proceso", font=("Segoe UI", 8, "bold"),
                                  bg=self.surface, fg=self.accent, relief="flat", cursor="hand2",
                                  command=self.on_trim_selected_process)
        btn_trim_proc.pack(side="left", padx=(0, 6))

        btn_add_white = tk.Button(act_frame, text="🛡️ Proteger (Añadir a Whitelist)", font=("Segoe UI", 8),
                                  bg=self.surface, fg=self.texto, relief="flat", cursor="hand2",
                                  command=self.on_whitelist_selected_process)
        btn_add_white.pack(side="left")

    # ---------- PESTAÑA 3: CONFIGURACIÓN Y EXCLUSIONES ----------
    def build_tab_settings(self):
        pad = tk.Frame(self.tab_cfg, bg=self.bg, padx=10, pady=10)
        pad.pack(fill="both", expand=True)

        # Minimizar a bandeja
        self.min_tray_var = tk.BooleanVar(value=self.cfg.get("minimize_to_tray", True))
        chk_tray = tk.Checkbutton(pad, text="Minimizar a la Bandeja del Sistema al cerrar la ventana",
                                  variable=self.min_tray_var, bg=self.bg, fg=self.texto,
                                  selectcolor=self.surface, activebackground=self.bg,
                                  font=("Segoe UI", 9), command=self.save_current_settings)
        chk_tray.pack(anchor="w", pady=(0, 10))

        # Lista de exclusiones
        tk.Label(pad, text="Lista de Exclusión de Procesos (Whitelist):", font=("Segoe UI", 9, "bold"),
                 bg=self.bg, fg=self.texto).pack(anchor="w")
        tk.Label(pad, text="Los procesos en esta lista no serán tocados durante la optimización.",
                 font=("Segoe UI", 8), bg=self.bg, fg=self.subtext).pack(anchor="w", pady=(0, 6))

        list_frame = tk.Frame(pad, bg=self.card)
        list_frame.pack(fill="both", expand=True)

        self.listbox_white = tk.Listbox(list_frame, bg="#11111b", fg=self.texto,
                                        selectbackground=self.surface, selectforeground=self.accent,
                                        font=("Consolas", 9), relief="flat")
        self.listbox_white.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.listbox_white.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox_white.config(yscrollcommand=scrollbar.set)

        for p in sorted(self.cfg.get("whitelist", [])):
            self.listbox_white.insert("end", p)

        # Botones lista
        btn_box = tk.Frame(pad, bg=self.bg)
        btn_box.pack(fill="x", pady=8)

        btn_add = tk.Button(btn_box, text="➕ Agregar Proceso", font=("Segoe UI", 8, "bold"),
                            bg=self.surface, fg=self.accent, relief="flat", cursor="hand2",
                            command=self.on_add_whitelist_manual)
        btn_add.pack(side="left", padx=(0, 6))

        btn_del = tk.Button(btn_box, text="🗑️ Eliminar Seleccionado", font=("Segoe UI", 8),
                            bg=self.surface, fg=self.warn, relief="flat", cursor="hand2",
                            command=self.on_remove_whitelist)
        btn_del.pack(side="left")

    # ---------- Lógica de Ajustes ----------
    def save_current_settings(self):
        self.cfg["umbral"] = int(self.umbral_var.get())
        self.cfg["intervalo"] = max(15, int(self.intervalo_var.get()))
        self.cfg["auto_opt"] = bool(self.auto_var.get())
        self.cfg["minimize_to_tray"] = bool(self.min_tray_var.get())
        save_config(self.cfg)

    def on_scale_change(self, v):
        self.lbl_umbral.config(text=f"{int(float(v))}%")
        self.save_current_settings()

    def on_toggle_auto(self):
        self.save_current_settings()
        if self.auto_var.get():
            self.log_msg(f"Modo automático ACTIVADO (umbral {self.umbral_var.get()}%).")
        else:
            self.log_msg("Modo automático DESACTIVADO.")

    def on_add_whitelist_manual(self):
        nombre = simpledialog.askstring("Agregar Proceso", "Nombre del ejecutable (ej. juego.exe):", parent=self.root)
        if nombre:
            nombre = nombre.strip().lower()
            if not nombre.endswith(".exe"):
                nombre += ".exe"
            wl = self.cfg.get("whitelist", [])
            if nombre not in wl:
                wl.append(nombre)
                self.cfg["whitelist"] = wl
                save_config(self.cfg)
                self.listbox_white.insert("end", nombre)
                self.log_msg(f"Agregado a exclusiones: {nombre}")

    def on_remove_whitelist(self):
        sel = self.listbox_white.curselection()
        if sel:
            item = self.listbox_white.get(sel[0])
            wl = self.cfg.get("whitelist", [])
            if item in wl:
                wl.remove(item)
                self.cfg["whitelist"] = wl
                save_config(self.cfg)
                self.listbox_white.delete(sel[0])
                self.log_msg(f"Removido de exclusiones: {item}")

    def on_whitelist_selected_process(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Selección", "Por favor selecciona un proceso de la tabla.")
            return
        item = self.tree.item(sel[0])
        pname = item["values"][1].lower()
        wl = self.cfg.get("whitelist", [])
        if pname not in wl:
            wl.append(pname)
            self.cfg["whitelist"] = wl
            save_config(self.cfg)
            self.listbox_white.insert("end", pname)
            messagebox.showinfo("Exclusiones", f"{pname} ha sido protegido y agregado a la lista de exclusiones.")
            self.log_msg(f"Protegido en exclusiones: {pname}")

    def on_trim_selected_process(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Selección", "Por favor selecciona un proceso de la tabla.")
            return
        item = self.tree.item(sel[0])
        pid = int(item["values"][0])
        pname = item["values"][1]
        ok = empty_single_process(pid)
        if ok:
            self.log_msg(f"Working Set vaciado exitosamente para PID {pid} ({pname}).")
            self.actualizar_top_procesos()
        else:
            self.log_msg(f"No se pudo vaciar PID {pid} (permisos insuficientes o finalizado).")

    # ---------- Thread-Safe Logging ----------
    def log_msg(self, texto):
        hora = datetime.datetime.now().strftime("%H:%M:%S")
        linea = f"[{hora}] {texto}"
        print(linea)

        def append_log():
            try:
                self.log.configure(state="normal")
                self.log.insert("end", linea + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
            except Exception:
                pass

        self.root.after(0, append_log)

    # ---------- Monitoreo y UI Loop ----------
    def actualizar_ui(self):
        try:
            mem = psutil.virtual_memory()
            total_gb = mem.total / (1024 ** 3)
            usado_gb = mem.used / (1024 ** 3)
            disp_gb = mem.available / (1024 ** 3)

            self.lbl_porcentaje.config(text=f"{mem.percent:.1f}%")
            if mem.percent >= 85:
                self.lbl_porcentaje.config(fg=self.warn)
            elif mem.percent >= 70:
                self.lbl_porcentaje.config(fg="#fab387")
            else:
                self.lbl_porcentaje.config(fg=self.texto)

            self.barra["value"] = mem.percent
            self.lbl_detalle.config(
                text=f"Total: {total_gb:.1f} GB  |  En uso: {usado_gb:.1f} GB  |  Libre: {disp_gb:.1f} GB"
            )

            # Modo automático
            if self.auto_var.get() and not self.optimizando:
                ahora = time.time()
                intervalo = max(15, int(self.intervalo_var.get()))
                if ahora - self.ultima_auto >= intervalo:
                    if mem.percent >= int(self.umbral_var.get()):
                        self.ultima_auto = ahora
                        self.log_msg(f"Auto: Uso {mem.percent:.1f}% >= umbral {self.umbral_var.get()}%. Optimizando...")
                        threading.Thread(target=self._optimizar_fondo, daemon=True).start()
                    else:
                        self.ultima_auto = ahora
        except Exception as e:
            self.log_msg(f"Error monitoreo: {e}")

        self.root.after(1000, self.actualizar_ui)

    def actualizar_top_procesos(self):
        def fetch_and_populate():
            procs = get_top_ram_processes(15)
            def update_tree():
                for item in self.tree.get_children():
                    self.tree.delete(item)
                for p in procs:
                    self.tree.insert("", "end", values=(p["pid"], p["name"], f"{p['ram_mb']:.1f} MB"))
            self.root.after(0, update_tree)

        threading.Thread(target=fetch_and_populate, daemon=True).start()

    # ---------- Optimización de Memoria ----------
    def on_optimizar(self):
        if self.optimizando:
            return
        threading.Thread(target=self._optimizar_fondo, daemon=True).start()

    def _optimizar_fondo(self):
        self.optimizando = True
        self.root.after(0, lambda: self.btn_optimizar.config(text="⏳ LIMPIANDO...", state="disabled"))

        try:
            mem_antes = psutil.virtual_memory()
            usado_antes_mb = mem_antes.used / (1024 ** 2)

            self.log_msg("Iniciando optimización...")
            gc.collect()

            # 1. Working Sets con Whitelist
            wl = self.cfg.get("whitelist", [])
            ok, fail, skip = empty_working_sets(wl)
            self.log_msg(f"Working Sets: {ok} vaciados, {skip} protegidos en whitelist, {fail} omitidos")

            # 2. Caché de archivos de sistema
            if clear_system_file_cache():
                self.log_msg("Caché de archivos del sistema liberada.")
            else:
                self.log_msg("Caché de sistema: omitida (ejecuta como Administrador para activarla).")

            # 3. Purga Standby List
            if purge_standby_list():
                self.log_msg("Standby List purgada exitosamente.")
            else:
                self.log_msg("Standby List: omitida (requiere permisos de Administrador).")

            gc.collect()
            time.sleep(1.2)

            mem_despues = psutil.virtual_memory()
            usado_despues_mb = mem_despues.used / (1024 ** 2)
            liberado = max(0, usado_antes_mb - usado_despues_mb)
            self.total_liberado += liberado

            self.log_msg(f"Listo. Liberado aprox: {liberado:.0f} MB | Uso actual: {mem_despues.percent:.1f}%")

            def finish_ui():
                self.lbl_liberado.config(text=f"Total liberado esta sesión: {self.total_liberado:.0f} MB")
                self.btn_optimizar.config(text="🧹 OPTIMIZAR AHORA", state="normal")
                self.actualizar_top_procesos()

            self.root.after(0, finish_ui)

        except Exception as e:
            self.log_msg(f"Error durante optimización: {e}")
            self.root.after(0, lambda: self.btn_optimizar.config(text="🧹 OPTIMIZAR AHORA", state="normal"))
        finally:
            self.optimizando = False

    # ---------- System Tray (Bandeja del Sistema) ----------
    def init_tray_icon(self):
        try:
            if os.path.exists(self.png_path):
                img = Image.open(self.png_path)
            elif os.path.exists(self.ico_path):
                img = Image.open(self.ico_path)
            else:
                img = Image.new("RGB", (64, 64), color="#00d4a4")

            menu = pystray.Menu(
                pystray.MenuItem("Abrir RAMCore", self.show_window, default=True),
                pystray.MenuItem("🧹 Optimizar Ahora", lambda: self.on_optimizar()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Salir", self.exit_app)
            )

            self.tray_icon = pystray.Icon("RAMCore", img, "RAMCore - Memory Optimizer", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print(f"No se pudo iniciar icono de bandeja: {e}")

    def on_close_window(self):
        if self.min_tray_var.get() and HAVE_PYSTRAY and self.tray_icon:
            self.root.withdraw()
        else:
            self.exit_app()

    def show_window(self, icon=None, item=None):
        self.root.after(0, self._restore_window)

    def _restore_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def exit_app(self, icon=None, item=None):
        self.save_current_settings()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.after(0, self.root.destroy)
        sys.exit(0)

# ---------- Entrada Principal ----------
def main():
    root = tk.Tk()
    app = RAMOptimizerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
