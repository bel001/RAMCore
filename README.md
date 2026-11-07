# ⚡ RAMCore - Windows Memory Optimizer

[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue.svg)](https://microsoft.com/windows)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**RAMCore** es una utilidad de optimización y monitorización de memoria RAM en tiempo real para Windows. Inspirada en herramientas avanzadas de administración interna como *RAMMap (Sysinternals)*, permite liberar memoria residual, vaciar conjuntos de trabajo (*working sets*), proteger procesos críticos mediante listas de exclusión y purgar la caché de archivos y páginas en espera (*standby*) con privilegios de Administrador.

---

## 📸 Interfaz Moderna por Pestañas

- **⚡ Optimización**: Métricas en vivo de RAM, botón de limpieza inmediata, selector de umbral y monitor automático en segundo plano.
- **📊 Top Procesos**: Vista en vivo de los procesos que más memoria consumen, con opción de limpiar un proceso individual o agregarlo a la lista de exclusiones.
- **⚙️ Ajustes & Exclusiones**: Gestor de lista blanca (*Whitelist*), minimización a la bandeja del sistema (*System Tray*) y botón para elevar a Administrador.

---

## ✨ Características Principales

- 🔄 **Modo Automático en Segundo Plano**: Supervisa periódicamente el consumo y dispara la limpieza únicamente si se supera el umbral configurado (ej. 75%).
- 🛡️ **Lista de Exclusión de Procesos (Whitelist)**: Protege juegos, navegadores o herramientas de trabajo para evitar el *stuttering* causado por la paginación a disco.
- 📌 **Minimización a la Bandeja del Sistema (System Tray)**: Permite ocultar la ventana en la barra de tareas y mantener la protección en segundo plano con acceso rápido desde el icono de notificación.
- 📊 **Monitor Top Consumidores de RAM**: Identifica con un clic qué procesos están saturando la memoria del equipo.
- 💾 **Persistencia de Ajustes (`config.json`)**: Guarda tus preferencias automáticamente (umbral, intervalo, modo automático, lista blanca y bandeja).
- 🧠 **Técnicas de Limpieza Profunda**:
  - **EmptyWorkingSet & Trim**: Desalojo y recorte de memoria no esencial en procesos activos.
  - **Purga de Caché de Archivos del Sistema**: Vaciado del búfer de lectura vía `SetSystemFileCacheSize` (con privilegios de Administrador).
  - **Standby List Flush**: Purga de páginas en espera vía `NtSetSystemInformation` habilitando `SeIncreaseQuotaPrivilege` y `SeProfileSingleProcessPrivilege`.
  - **Recolección de Basura**: Ejecución forzada de `gc.collect()`.
- 📦 **Compilación a `.EXE`**: Incluye script `build.bat` para empaquetar la aplicación en un ejecutable independiente con PyInstaller.

---

## 🛠️ Requisitos e Instalación

### Requisitos
- **Sistema Operativo**: Windows 10 / Windows 11 (64-bit recomendado).
- **Python**: 3.10 o superior (o el ejecutable `.exe` compilado).

### Instalación
1. Clona el repositorio:
   ```bash
   git clone https://github.com/bel001/RAMCore.git
   cd RAMCore
   ```

2. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🚀 Uso

### Ejecución Directa
```bash
python ram_optimizer.py
```

### Ejecución en Segundo Plano (Sin Consola)
- Haz doble clic en **`RAM_Optimizer.vbs`** o **`RAM_Optimizer.bat`**.

### Compilación a Ejecutable `.EXE`
- Ejecuta el script **`build.bat`**. Al finalizar, encontrarás tu ejecutable independiente en:
  ```text
  dist\RAMCore.exe
  ```

---

## ⚙️ ¿Cómo Funciona la Optimización en Windows?

A diferencia de limpiadores placebo, RAMCore utiliza APIs nativas del subsistema de Windows (`kernel32.dll`, `psapi.dll`, `advapi32.dll` y `ntdll.dll`):

1. **`EmptyWorkingSet` & `SetProcessWorkingSetSize(-1, -1)`**: Solicita al gestor de memoria virtual de Windows (*Virtual Memory Manager*) que desaloje las páginas físicas que los procesos no están usando activamente.
2. **`SetSystemFileCacheSize(-1, -1, 0)`**: Libera la memoria consumida por lecturas y escrituras previas en disco.
3. **`AdjustTokenPrivileges` + `NtSetSystemInformation(80, ...)`**: Eleva los privilegios de token NT para ejecutar `MemoryPurgeStandbyList` y vaciar la memoria en lista de espera sin reiniciar el equipo.

---

## 🗺️ Hoja de Ruta (Roadmap)

- [x] Minimización a la Bandeja del Sistema (System Tray con menú contextual).
- [x] Lista de exclusión de procesos (Whitelist) para evitar stutter en juegos o aplicaciones críticas.
- [x] Monitor de procesos con mayor consumo de memoria (Top RAM).
- [x] Persistencia de configuración en `config.json`.
- [x] Privilegios reales NT (`AdjustTokenPrivileges`) y botón de elevación UAC.
- [x] Script de compilación a ejecutable `.exe` (`build.bat`).
- [ ] Opción en interfaz para "Iniciar con Windows" (registro Run).

---

## 📄 Licencia

Distribuido bajo la Licencia MIT.
