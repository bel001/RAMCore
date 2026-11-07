# ⚡ RAMCore - Windows Memory Optimizer

[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue.svg)](https://microsoft.com/windows)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**RAMCore** es una utilidad de optimización y monitorización de memoria RAM en tiempo real para Windows. Inspirada en herramientas avanzadas de administración interna como *RAMMap (Sysinternals)*, permite liberar memoria residual, vaciar conjuntos de trabajo (*working sets*) y purgar la caché de archivos del sistema de forma manual o automática.

---

## 📸 Vista General

```text
+------------------------------------------+
|            ⚡ RAM OPTIMIZER              |
|   Limpieza automática estilo RAMMap      |
|                                          |
|                 [ 78.4% ]                |
|  [==========================......]      |
|  Total: 16.0 GB | En uso: 12.5 GB        |
|                                          |
|         [ 🧹 OPTIMIZAR AHORA ]           |
|                                          |
|  [x] Modo Automático                     |
|  Optimizar si supera: [---o---] 75%      |
|  Revisar cada: [60] seg                  |
+------------------------------------------+
```

---

## ✨ Características Principales

- 🔄 **Modo Automático en Segundo Plano**: Supervisa continuamente el consumo y dispara la limpieza únicamente cuando se supera un umbral configurable (ej. 75%).
- 🧠 **Técnicas de Limpieza Profunda**:
  - **EmptyWorkingSet**: Desalojo del working set de los procesos de usuario.
  - **SetProcessWorkingSetSize Trim**: Reducción controlada de las cuotas de memoria asignadas a procesos activos.
  - **Purga de Caché del Sistema (File Cache)**: Vaciado del búfer de lectura de archivos vía `SetSystemFileCacheSize` (requiere privilegios de Administrador).
  - **Standby List Flush**: Purga de páginas en espera mediante `NtSetSystemInformation` (requiere privilegios de Administrador).
  - **Recolección de Basura**: Ejecución forzada de `gc.collect()`.
- 📊 **Monitor en Tiempo Real**: Visualización reactiva con indicadores de color dinámicos según el nivel de saturación de la memoria.
- 🔕 **Ejecución Silenciosa**: Scripts incluidos (`.bat` y `.vbs`) para operar sin ventanas de terminal abiertas.

---

## 🛠️ Requisitos e Instalación

### Requisitos
- **Sistema Operativo**: Windows 10 / Windows 11 (64-bit recomendado).
- **Python**: 3.10 o superior.

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

### Ejecución Estándar (Interfaz Gráfica)
```bash
python ram_optimizer.py
```

### Ejecución con Privilegios Elevados (Recomendado)
Para desbloquear la purga de la **Standby List** y la **Caché del Sistema**, abre PowerShell o CMD como **Administrador** y ejecuta:
```bash
python ram_optimizer.py
```

### Ejecución Silenciosa / Segundo Plano
- Haz doble clic en **`RAM_Optimizer.vbs`** o **`RAM_Optimizer.bat`** para lanzar el optimizador sin dejar una consola CMD visible.

---

## ⚙️ ¿Cómo Funciona la Optimización en Windows?

A diferencia de optimizadores placebo comunes, RAMCore utiliza llamadas directas a las APIs del núcleo de Windows (`kernel32.dll`, `psapi.dll` y `ntdll.dll`):

1. **`EmptyWorkingSet` & `SetProcessWorkingSetSize`**: Indica al Administrador de Memoria de Windows que recorte las páginas físicas no esenciales de cada proceso y las traslade al archivo de paginación o las marque como disponibles.
2. **`SetSystemFileCacheSize(-1, -1, 0)`**: Fuerza el vaciado de páginas en caché del sistema de archivos.
3. **`NtSetSystemInformation(80, ...)`**: Invoca la orden `MemoryPurgeStandbyList` a nivel NT para liberar memoria en espera y convertirla en memoria libre de inmediato.

---

## 🗺️ Hoja de Ruta (Roadmap)

- [ ] Minimización a la Bandeja del Sistema (System Tray con menú contextual).
- [ ] Lista de exclusión de procesos (Whitelist) para evitar stutter en juegos o IDEs.
- [ ] Panel con el Top 5 de procesos con mayor consumo de memoria.
- [ ] Persistencia de ajustes en `config.json`.
- [ ] Opción en interfaz para "Iniciar con Windows" (registro Run).
- [ ] Compilado standalone en `.exe` sin requerir Python preinstalado.

---

## 📄 Licencia

Distribuido bajo la Licencia MIT. Consulta `LICENSE` para más información.
