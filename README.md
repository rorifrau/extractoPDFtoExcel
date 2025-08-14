# extractoPDFtoExcel

Aplicación en Python + Streamlit para extraer información de extractos PDF y exportarla a Excel.

Esta guía está optimizada para Windows (PowerShell/CMD/VS Code) e incluye: creación/activación de entornos virtuales (venv), instalación de dependencias, ejecución con Streamlit, exportación de `requirements.txt`, e integración con Git.

## Requisitos

- Python 3.12.10 instalado.
- Verificar en terminal (CMD/PowerShell/VS Code):

```bash
python --version
```

Nota: En Windows puedes usar indistintamente `python` o `py`.

## Instalación rápida (TL;DR)

```bash
# 1) Crear venv (recomendado: .venv en la raíz)
python -m venv .venv

# 2) Activar venv
# PowerShell
.\.venv\Scripts\Activate.ps1
# CMD
.\.venv\Scripts\activate.bat

# 3) Actualizar pip
python -m pip install --upgrade pip

# 4) Instalar dependencias
pip install -r requirements.txt

# 5) Ejecutar la app
python -m streamlit run app.py
```

Si PowerShell bloquea la activación del venv:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Guía práctica (Windows)

### 0) Requisitos
- Python 3.12.10 instalado y accesible en PATH.

### 1) Crear el entorno virtual
- Recomendado (nombre oculto y fácil de ignorar en Git):

```bash
python -m venv .venv
# Alternativa Windows
py -m venv .venv
```

> También funciona con otro nombre (p. ej. `extractoPDFtoExcel`), pero `.venv` simplifica el `.gitignore`.

### 2) Activar el entorno virtual
- PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

- CMD:

```bat
.\.venv\Scripts\activate.bat
```

Al activarse, verás el prefijo `(.venv)` en el prompt.

Si PowerShell bloquea la activación:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 3) Actualizar pip

```bash
python -m pip install --upgrade pip
```

### 4) Instalar dependencias del proyecto
- Si ya tienes `requirements.txt`:

```bash
pip install -r requirements.txt
```

- Si aún no existe, instala manualmente lo básico y luego congela:

```bash
pip install streamlit pandas openpyxl pypdf2
```

### 5) Congelar dependencias

```bash
pip freeze > requirements.txt
```

### 6) Ejecutar la app con Streamlit

```bash
python -m streamlit run app.py
# o simplemente
streamlit run app.py
```

- Detener: Ctrl + C
- Puerto por defecto: `http://localhost:8501`
- Cambiar puerto:

```bash
streamlit run app.py --server.port 8502
```

### 7) Desactivar el entorno

```bash
deactivate
```

### 8) Eliminar el entorno

```bash
rmdir /s /q .venv
```

### 9) Integración con VS Code
1. Abrir la carpeta del proyecto.
2. Instalar la extensión "Python" (Microsoft).
3. `Ctrl+Shift+P` → "Python: Select Interpreter" → elegir el de `.venv`.
4. Activar el venv en la terminal integrada.
5. Ejecutar: `python -m streamlit run app.py`.

### 10) Flujo de trabajo recomendado
1. Crear venv.
2. Activar venv.
3. Actualizar pip.
4. Instalar dependencias.
5. Congelar dependencias.
6. Ejecutar con Streamlit.
7. Desactivar venv.

### 11) Problemas comunes y tips
- "No se reconoce 'streamlit'" → instala dentro del venv activo.
- Varias versiones de Python → usa: `py -3.12 -m venv .venv`.
- Ignorar venv en Git → revisa el `.gitignore` incluido.
- PDFs de entrada muy grandes → no los subas al repositorio; usa una carpeta `samples/` y agrega reglas al `.gitignore`.

### 12) Estructura típica del proyecto

```text
extractoPDFtoExcel/
    app.py
    operaciones_fraccionadas.py
    utils.py
    requirements.txt
    README.md
    .gitignore
    .venv/                # entorno virtual (recomendado, ignorado por Git)
    samples/              # PDFs de ejemplo (opcional, ignorado por Git)
```

### 13) Cheatsheet

```text
Crear venv:   python -m venv .venv
Activar PS:   .\.venv\Scripts\Activate.ps1
Activar CMD:  .\.venv\Scripts\activate.bat
Actualizar:   python -m pip install --upgrade pip
Instalar:     pip install -r requirements.txt
Streamlit:    python -m streamlit run app.py
Exportar:     pip freeze > requirements.txt
Salir:        deactivate
Eliminar:     rmdir /s /q .venv
```

## Git: inicializar y subir el repositorio

Este proyecto incluye un `.gitignore` que evita subir el entorno virtual, archivos temporales y PDFs grandes. Pasos típicos:

```bash
# 1) Inicializar repo local
git init
git branch -M main

# 2) Añadir y hacer primer commit
git add .
git commit -m "Inicializa proyecto con README y .gitignore"

# 3) Crear un repositorio vacío en GitHub/GitLab/Bitbucket
# 4) Añadir remoto (ejemplo GitHub)
git remote add origin https://github.com/<usuario>/<repo>.git

# 5) Subir rama principal
git push -u origin main
```

Si ya habías creado un venv dentro de la carpeta del proyecto con nombre distinto (p. ej. `Include/`, `Lib/`, `Scripts/`, `pyvenv.cfg`), el `.gitignore` impedirá que se agregue en el primer commit. Si esos archivos ya estuvieran siendo rastreados por Git, usa:

```bash
git rm -r --cached Include Lib Scripts pyvenv.cfg
git commit -m "Deja de rastrear venv del repositorio"
```

## Notas adicionales
- Recomendación: usa `.venv` en la raíz del proyecto en lugar de crear un venv con el nombre del proyecto. Es más limpio y estándar, y simplifica el `.gitignore`.
- Considera mantener PDFs de ejemplo en `samples/` y no subir PDFs reales al repositorio.


