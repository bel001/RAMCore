"""
RAM Optimizer Automático - estilo RAMMap simplificado
- Ventana de escritorio normal (tkinter)
- Optimización automática por umbral
- Limpieza: EmptyWorkingSet + Trim + caché + GC
- Funciona sin admin (mejor con admin para caché del sistema)
"""
import ctypes
import gc
import os
import sys
import threading
import time
import datetime
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import psutil
except ImportError:
    raise SystemExit("Falta psutil. Instala con: pip install psutil")

# ---------- Optimizador núcleo Windows ----------
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi if hasattr(ctypes.windll, "psapi") else kernel32

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_SET_QUOTA = 0x0100

def log_msg(texto, widget=None):
    hora = datetime.datetime.now().strftime("%H:%M:%S")
    linea = f"[{hora}] {texto}"
    print(linea)
    if widget is not None:
        try:
            widget.configure(state="normal")
            widget.insert("end", linea + "\n")
            widget.see("end")
            widget.configure(state="disabled")
        except Exception:
            pass

def empty_working_sets():
    """Vacía Working Set de todos los procesos (como RAMMap > Empty Working Sets)."""
    count_ok = 0
    count_fail = 0
    for proc in psutil.process_iter(["pid"]):
        try:
            h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, proc.info["pid"])
            if not h:
                count_fail += 1
                continue
            try:
                # 1) EmptyWorkingSet
                try:
                    kernel32.EmptyWorkingSet(h)
                except Exception:
                    pass
                # 2) Trim: SetProcessWorkingSetSize(-1, -1)
                try:
                    kernel32.SetProcessWorkingSetSize(h, ctypes.c_size_t(-1), ctypes.c_size_t(-1))
                except Exception:
                    pass
                count_ok += 1
            finally:
                kernel32.CloseHandle(h)
        except Exception:
            count_fail += 1
    return count_ok, count_fail

def clear_system_file_cache():
    """Intenta vaciar caché de archivos del sistema (como RAMMap > Empty Standby). Requiere privilegios."""
    try:
        # SetSystemFileCacheSize(-1, -1, 0) = flush
        res = kernel32.SetSystemFileCacheSize(ctypes.c_size_t(-1), ctypes.c_size_t(-1), 0)
        return bool(res)
    except Exception:
        return False

def purge_standby_list():
    """Intenta purgar Standby List vía NtSetSystemInformation. Devuelve True si lo logró."""
    try:
        ntdll = ctypes.windll.ntdll
        # SystemMemoryListInformation = 80
        # MemoryPurgeStandbyList = 4
        class SYSTEM_MEMORY_LIST_COMMAND(ctypes.Structure):
            _fields_ = [("Command", ctypes.c_int)]
        cmd = SYSTEM_MEMORY_LIST_COMMAND(4)
        status = ntdll.NtSetSystemInformation(80, ctypes.byref(cmd), ctypes.sizeof(cmd))
        return status == 0
    except Exception:
        return False

def optimizar_ram(log_widget=None):
    """Ejecuta optimización completa. Devuelve MB liberados."""
    mem_antes = psutil.virtual_memory()
    usado_antes_mb = mem_antes.used / 1024 / 1024

    log_msg("Iniciando optimización...", log_widget)

    # 1. GC Python
    gc.collect()

    # 2. Working sets (lo más efectivo sin driver)
    ok, fail = empty_working_sets()
    log_msg(f"Working Sets vaciados: {ok} procesos OK, {fail} omitidos", log_widget)

    # 3. Caché sistema
    if clear_system_file_cache():
        log_msg("Caché de archivos del sistema liberada", log_widget)
    else:
        log_msg("Caché sistema: omitida (ejecuta como Admin para activarla)", log_widget)

    # 4. Standby list
    if purge_standby_list():
        log_msg("Standby List purgada", log_widget)
    else:
        log_msg("Standby List: no se pudo purgar (normal sin Admin)", log_widget)

    # 5. GC final + pequeña espera para que Windows actualice contadores
    gc.collect()
    time.sleep(1.2)

    mem_despues = psutil.virtual_memory()
    usado_despues_mb = mem_despues.used / 1024 / 1024
    liberado = usado_antes_mb - usado_despues_mb
    if liberado < 0:
        liberado = 0
    log_msg(f"Listo. Liberado aprox: {liberado:.0f} MB | Uso: {mem_despues.percent:.1f}%", log_widget)
    return liberado

# ---------- GUI ----------
class RAMOptimizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RAM Optimizer Automático")
        self.root.geometry("460x640")
        self.root.resizable(False, False)

        # Icono si existe
        base = os.path.dirname(os.path.abspath(__file__))
        ico = os.path.join(base, "icono.ico")
        if os.path.exists(ico):
            try:
                self.root.iconbitmap(ico)
            except Exception:
                pass

        # Estilo oscuro moderno
        self.bg = "#1e1e2e"
        self.card = "#2a2a3f"
        self.accent = "#00d4a4"
        self.texto = "#ffffff"
        self.root.configure(bg=self.bg)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TProgressbar", background=self.accent, troughcolor=self.card,
                        borderwidth=0, thickness=14)

        # Título
        tk.Label(root, text="⚡ RAM OPTIMIZER", font=("Segoe UI", 20, "bold"),
                 bg=self.bg, fg=self.accent).pack(pady=(15, 2))
        tk.Label(root, text="Limpieza automática estilo RAMMap", font=("Segoe UI", 10),
                 bg=self.bg, fg="#aaaaaa").pack(pady=(0, 10))

        # Tarjeta estado
        frame = tk.Frame(root, bg=self.card, padx=15, pady=12)
        frame.pack(fill="x", padx=15)

        self.lbl_porcentaje = tk.Label(frame, text="--%", font=("Segoe UI", 32, "bold"),
                                       bg=self.card, fg=self.texto)
        self.lbl_porcentaje.pack()

        self.barra = ttk.Progressbar(frame, length=380, mode="determinate", style="TProgressbar")
        self.barra.pack(pady=8)

        self.lbl_detalle = tk.Label(frame, text="Cargando...", font=("Segoe UI", 9),
                                    bg=self.card, fg="#cccccc")
        self.lbl_detalle.pack()

        self.lbl_liberado = tk.Label(frame, text="Total liberado esta sesión: 0 MB",
                                     font=("Segoe UI", 9, "bold"), bg=self.card, fg=self.accent)
        self.lbl_liberado.pack(pady=(6, 0))

        # Botones
        btn_frame = tk.Frame(root, bg=self.bg)
        btn_frame.pack(pady=12)

        self.btn_optimizar = tk.Button(btn_frame, text="🧹 OPTIMIZAR AHORA", font=("Segoe UI", 11, "bold"),
                                       bg=self.accent, fg="#000000", width=22, height=2,
                                       relief="flat", cursor="hand2", command=self.on_optimizar)
        self.btn_optimizar.pack()

        # Automático
        auto_frame = tk.Frame(root, bg=self.card, padx=15, pady=12)
        auto_frame.pack(fill="x", padx=15)

        self.auto_var = tk.BooleanVar(value=False)
        self.chk_auto = tk.Checkbutton(auto_frame, text="Modo Automático (optimiza solo cuando se necesita)",
                                       variable=self.auto_var, bg=self.card, fg=self.texto,
                                       selectcolor=self.card, activebackground=self.card,
                                       font=("Segoe UI", 9, "bold"), command=self.on_toggle_auto)
        self.chk_auto.pack(anchor="w")

        tk.Label(auto_frame, text="Optimizar si la RAM supera:", bg=self.card, fg="#cccccc",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))

        umbral_frame = tk.Frame(auto_frame, bg=self.card)
        umbral_frame.pack(fill="x")
        self.umbral_var = tk.IntVar(value=75)
        self.scale = tk.Scale(umbral_frame, from_=50, to=95, orient="horizontal",
                              variable=self.umbral_var, bg=self.card, fg=self.texto,
                              highlightthickness=0, length=300)
        self.scale.pack(side="left")
        self.lbl_umbral = tk.Label(umbral_frame, text="75%", bg=self.card, fg=self.accent,
                                   font=("Segoe UI", 11, "bold"), width=5)
        self.lbl_umbral.pack(side="left")
        self.scale.configure(command=lambda v: self.lbl_umbral.config(text=f"{int(float(v))}%"))

        tk.Label(auto_frame, text="Revisar cada (segundos):", bg=self.card, fg="#cccccc",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 0))
        self.intervalo_var = tk.IntVar(value=60)
        tk.Spinbox(auto_frame, from_=15, to=600, textvariable=self.intervalo_var,
                   width=8, font=("Segoe UI", 9)).pack(anchor="w")

        # Log
        tk.Label(root, text="Registro:", bg=self.bg, fg="#aaaaaa", font=("Segoe UI", 9)).pack(anchor="w", padx=18)
        self.log = tk.Text(root, height=8, bg="#11111b", fg="#00ffaa", font=("Consolas", 8),
                           relief="flat", state="disabled")
        self.log.pack(fill="x", padx=15, pady=(0, 10))

        # Footer
        tk.Label(root, text="💡 Consejo: ejecútalo como Administrador para limpieza profunda",
                 bg=self.bg, fg="#777788", font=("Segoe UI", 8)).pack(side="bottom", pady=8)

        self.total_liberado = 0.0
        self.optimizando = False
        self.ultima_auto = 0

        log_msg("RAM Optimizer iniciado. Pulsa OPTIMIZAR o activa el modo automático.", self.log)
        self.actualizar_ui()

    def actualizar_ui(self):
        try:
            mem = psutil.virtual_memory()
            total_gb = mem.total / 1024 / 1024 / 1024
            usado_gb = mem.used / 1024 / 1024 / 1024
            disp_gb = mem.available / 1024 / 1024 / 1024

            self.lbl_porcentaje.config(text=f"{mem.percent:.1f}%")
            # color según uso
            if mem.percent >= 85:
                self.lbl_porcentaje.config(fg="#ff5555")
            elif mem.percent >= 70:
                self.lbl_porcentaje.config(fg="#ffbb33")
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
                        log_msg(f"Auto: uso {mem.percent:.1f}% >= umbral {self.umbral_var.get()}%. Optimizando...", self.log)
                        threading.Thread(target=self._optimizar_fondo, daemon=True).start()
                    else:
                        self.ultima_auto = ahora  # revisado, todo OK
        except Exception as e:
            log_msg(f"Error monitoreo: {e}", self.log)
        self.root.after(1000, self.actualizar_ui)

    def on_optimizar(self):
        if self.optimizando:
            return
        threading.Thread(target=self._optimizar_fondo, daemon=True).start()

    def _optimizar_fondo(self):
        self.optimizando = True
        try:
            self.btn_optimizar.config(text="⏳ LIMPIANDO...", state="disabled")
            lib = optimizar_ram(self.log)
            self.total_liberado += lib
            self.lbl_liberado.config(text=f"Total liberado esta sesión: {self.total_liberado:.0f} MB")
        finally:
            self.btn_optimizar.config(text="🧹 OPTIMIZAR AHORA", state="normal")
            self.optimizando = False

    def on_toggle_auto(self):
        if self.auto_var.get():
            log_msg(f"Modo automático ACTIVADO (umbral {self.umbral_var.get()}%)", self.log)
            messagebox.showinfo("RAM Optimizer", f"Modo automático activado.\nSe optimizará solo cuando la RAM supere el {self.umbral_var.get()}%.")
        else:
            log_msg("Modo automático DESACTIVADO", self.log)


def main():
    root = tk.Tk()
    app = RAMOptimizerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
