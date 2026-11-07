# RAMCore

Optimizador de memoria RAM automático para Windows estilo RAMMap simplificado con interfaz gráfica (Tkinter).

## 🚀 Características
- **Optimización automática**: Monitoreo continuo y optimización al superar un umbral configurable de uso de RAM.
- **Técnicas de limpieza avanzadas**:
  - `EmptyWorkingSet` de procesos de usuario y sistema.
  - Vaciado de conjuntos de trabajo (Trim).
  - Recolección de basura del sistema (`gc.collect`).
- **Monitoreo en tiempo real**: Visualización del consumo de memoria y porcentaje en tiempo real.
- **Ejecución silenciosa / en segundo plano**: Scripts incluidos para lanzar la aplicación sin ventana de consola (`RAM_Optimizer.vbs` y `RAM_Optimizer.bat`).

## 📋 Requisitos
- Windows 10 u 11
- Python 3.10 o superior

Instalar dependencias necesarias:
```bash
pip install -r requirements.txt
```

## 💻 Uso
Para iniciar la aplicación con interfaz gráfica:
```bash
python ram_optimizer.py
```

O iniciar sin consola a través de:
- `RAM_Optimizer.vbs` o `RAM_Optimizer.bat`
