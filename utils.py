"""
Módulo de utilidades para el convertidor de extractos bancarios.
Contiene funciones para Excel, debug, configuraciones y utilidades generales.

Versión 2.6 - Modular
"""

import pandas as pd
import io
import streamlit as st
from typing import Dict, List, Any, Optional
import re
from datetime import datetime

class ConfiguracionApp:
    """Configuraciones globales de la aplicación"""
    
    VERSION = "2.6"
    TITULO = "Convertidor de Extractos Bancarios PDF a Excel"
    
    # Patrones globales
    PATRONES_FECHA = r'\d{2}\.\d{2}\.\d{4}'
    PATRONES_IMPORTE = r'\d+[,\.]\d{2}'
    
    # Configuración de debug
    DEBUG_MAX_LINEAS_TEXTO = 4000
    DEBUG_MAX_MENCIONES = 15
    DEBUG_MAX_NUMEROS = 20
    
    # Configuración de Excel
    NOMBRE_ARCHIVO_DEFAULT = "extractoTarjeta.xlsx"
    HOJAS_EXCEL = {
        'resumen': 'Resumen',
        'fraccionadas': 'Operaciones Fraccionadas', 
        'periodo': 'Operaciones Período'
    }

class GeneradorExcel:
    """Clase especializada en generar archivos Excel"""
    
    def __init__(self):
        self.config = ConfiguracionApp()
    
    def crear_excel(self, info_general: Dict, operaciones_fraccionadas: List[Dict], operaciones_periodo: List[Dict]) -> bytes:
        """Crea un archivo Excel con los datos extraídos"""
        
        buffer = io.BytesIO()
        
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Crear hoja de resumen
            self._crear_hoja_resumen(writer, info_general, operaciones_fraccionadas, operaciones_periodo)
            
            # Crear hoja de operaciones fraccionadas
            if operaciones_fraccionadas:
                self._crear_hoja_fraccionadas(writer, operaciones_fraccionadas)
            
            # Crear hoja de operaciones del período
            if operaciones_periodo:
                self._crear_hoja_periodo(writer, operaciones_periodo)
        
        buffer.seek(0)
        return buffer.getvalue()
    
    def _crear_hoja_resumen(self, writer, info_general: Dict, operaciones_fraccionadas: List[Dict], operaciones_periodo: List[Dict]):
        """Crea la hoja de resumen con información general"""
        
        resumen_data = []
        
        # Encabezado
        resumen_data.append(['EXTRACTO BANCARIO MYCARD'])
        resumen_data.append([f'Generado el: {datetime.now().strftime("%d/%m/%Y %H:%M")}'])
        resumen_data.append([''])
        
        # Información general
        if 'titular' in info_general:
            resumen_data.append(['Titular', info_general['titular']])
        
        if 'periodo_inicio' in info_general and 'periodo_fin' in info_general:
            resumen_data.append(['Período', f"{info_general['periodo_inicio']} - {info_general['periodo_fin']}"])
        
        if 'limite_credito' in info_general:
            resumen_data.append(['Límite de crédito', f"{info_general['limite_credito']} €"])
        
        resumen_data.append([''])
        
        # Resumen de operaciones
        resumen_data.append(['RESUMEN DE OPERACIONES'])
        resumen_data.append(['Operaciones Fraccionadas', len(operaciones_fraccionadas)])
        resumen_data.append(['Operaciones del Período', len(operaciones_periodo)])
        
        # Totales
        if operaciones_fraccionadas:
            total_fraccionadas = sum(op.get('importe_operacion', 0) for op in operaciones_fraccionadas)
            resumen_data.append(['Total Fraccionadas', f"{total_fraccionadas:.2f} €"])
        
        if operaciones_periodo:
            total_periodo = sum(op.get('importe', 0) for op in operaciones_periodo)
            resumen_data.append(['Total Período', f"{total_periodo:.2f} €"])
        
        # Información técnica si hay operaciones fraccionadas
        if operaciones_fraccionadas:
            resumen_data.append([''])
            resumen_data.append(['INFORMACIÓN TÉCNICA'])
            
            # Agrupar por método de extracción
            metodos = {}
            for op in operaciones_fraccionadas:
                metodo = op.get('metodo_extraccion', 'desconocido')
                if metodo not in metodos:
                    metodos[metodo] = 0
                metodos[metodo] += 1
            
            resumen_data.append(['Métodos de extracción utilizados:'])
            for metodo, cantidad in metodos.items():
                resumen_data.append([f'  - {metodo}', cantidad])
        
        df_resumen = pd.DataFrame(resumen_data)
        df_resumen.to_excel(writer, sheet_name=self.config.HOJAS_EXCEL['resumen'], index=False, header=False)
    
    def _crear_hoja_fraccionadas(self, writer, operaciones_fraccionadas: List[Dict]):
        """Crea la hoja de operaciones fraccionadas"""
        
        df_fraccionadas = pd.DataFrame(operaciones_fraccionadas)
        
        # Reordenar columnas para mejor legibilidad
        columnas_orden = [
            'fecha', 'concepto', 'importe_operacion', 'importe_pendiente',
            'capital_amortizado', 'intereses', 'cuota_mensual', 'plazo',
            'importe_pendiente_despues', 'metodo_extraccion'
        ]
        
        # Reordenar solo las columnas que existen
        columnas_existentes = [col for col in columnas_orden if col in df_fraccionadas.columns]
        df_fraccionadas = df_fraccionadas[columnas_existentes]
        
        df_fraccionadas.to_excel(writer, sheet_name=self.config.HOJAS_EXCEL['fraccionadas'], index=False)
    
    def _crear_hoja_periodo(self, writer, operaciones_periodo: List[Dict]):
        """Crea la hoja de operaciones del período"""
        
        df_periodo = pd.DataFrame(operaciones_periodo)
        df_periodo.to_excel(writer, sheet_name=self.config.HOJAS_EXCEL['periodo'], index=False)
    
    def generar_nombre_archivo(self, nombre_pdf: str) -> str:
        """Genera un nombre de archivo Excel basado en el nombre del PDF"""
        
        if not nombre_pdf:
            return self.config.NOMBRE_ARCHIVO_DEFAULT
        
        # Buscar fecha en el nombre del PDF
        fecha_match = re.match(r'^(\d{1,2}\s+\w{3}\s+\d{4})', nombre_pdf)
        if fecha_match:
            fecha_extraida = fecha_match.group(1)
            return f"{fecha_extraida}_extractoTarjeta.xlsx"
        
        fecha_match2 = re.search(r'(\d{1,2})\s*(\w{3})\s*(\d{4})', nombre_pdf)
        if fecha_match2:
            dia = fecha_match2.group(1)
            mes = fecha_match2.group(2)
            año = fecha_match2.group(3)
            return f"{dia} {mes} {año}_extractoTarjeta.xlsx"
        
        # Usar nombre base del PDF si no se encuentra fecha
        nombre_base = nombre_pdf.replace('.pdf', '').replace('.PDF', '')
        return f"{nombre_base}_extractoTarjeta.xlsx"

class DebugHelper:
    """Clase para manejar información de debug de manera organizada"""
    
    def __init__(self):
        self.config = ConfiguracionApp()
    
    def mostrar_info_pdf(self, archivo_pdf, texto_extraido: str):
        """Muestra información básica del PDF"""
        if st.session_state.get('debug_mode', False):
            st.write(f"📄 **Información del PDF: {archivo_pdf.name}**")
            st.write(f"   📊 Tamaño del archivo: {len(archivo_pdf.read()) if hasattr(archivo_pdf, 'read') else 'N/A'} bytes")
            st.write(f"   📝 Texto extraído: {len(texto_extraido)} caracteres")
    
    def mostrar_estadisticas_texto(self, texto: str, pdf_id: str):
        """Muestra estadísticas del texto extraído"""
        if not st.session_state.get('debug_mode', False):
            return
        
        st.write(f"📊 **Estadísticas de texto - {pdf_id}**")
        
        # Estadísticas básicas
        lineas = texto.split('\n')
        palabras = texto.split()
        
        st.write(f"   📝 Líneas: {len(lineas)}")
        st.write(f"   🔤 Palabras: {len(palabras)}")
        st.write(f"   📊 Caracteres: {len(texto)}")
        
        # Menciones específicas
        menciones_caixa = len(re.findall(r'CAJ\.LA CAIXA', texto, re.IGNORECASE))
        menciones_bbva = len(re.findall(r'B\.B\.V\.A', texto, re.IGNORECASE))
        fechas = len(re.findall(self.config.PATRONES_FECHA, texto))
        numeros = len(re.findall(self.config.PATRONES_IMPORTE, texto))
        
        st.write(f"   🏦 Menciones CAJ.LA CAIXA: {menciones_caixa}")
        st.write(f"   🏦 Menciones B.B.V.A: {menciones_bbva}")
        st.write(f"   📅 Fechas encontradas: {fechas}")
        st.write(f"   💰 Números decimales: {numeros}")
    
    def mostrar_muestra_texto(self, texto: str, pdf_id: str, max_chars: int = None):
        """Muestra una muestra del texto extraído"""
        if not st.session_state.get('debug_mode', False):
            return
        
        if max_chars is None:
            max_chars = self.config.DEBUG_MAX_LINEAS_TEXTO
        
        st.text_area(
            f"🔍 Muestra de texto extraído - {pdf_id} (primeros {max_chars} caracteres)",
            texto[:max_chars],
            height=300,
            key=f"debug_muestra_{pdf_id}"
        )
    
    def mostrar_menciones_banco(self, texto: str, banco: str = "CAJ.LA CAIXA"):
        """Muestra las menciones específicas de un banco"""
        if not st.session_state.get('debug_mode', False):
            return
        
        menciones = re.findall(f'.*{banco}.*', texto, re.IGNORECASE)
        
        st.write(f"🏦 **Menciones de '{banco}': {len(menciones)}**")
        for i, mencion in enumerate(menciones[:self.config.DEBUG_MAX_MENCIONES]):
            st.write(f"   {i+1}. {mencion}")
        
        if len(menciones) > self.config.DEBUG_MAX_MENCIONES:
            st.write(f"   ... y {len(menciones) - self.config.DEBUG_MAX_MENCIONES} más")
    
    def mostrar_resumen_operaciones(self, operaciones: List[Dict], titulo: str):
        """Muestra un resumen de las operaciones encontradas"""
        if not st.session_state.get('debug_mode', False):
            return
        
        st.write(f"📋 **{titulo}: {len(operaciones)} operaciones**")
        
        if operaciones:
            # Mostrar primeras operaciones
            for i, op in enumerate(operaciones[:5]):
                fecha = op.get('fecha', 'N/A')
                concepto = op.get('concepto', op.get('establecimiento', 'N/A'))
                importe = op.get('importe_operacion', op.get('importe', 0))
                metodo = op.get('metodo_extraccion', 'N/A')
                
                st.write(f"   {i+1}. {fecha} - {concepto} - {importe}€")
                if metodo != 'N/A':
                    st.write(f"      └─ Método: {metodo}")
            
            if len(operaciones) > 5:
                st.write(f"   ... y {len(operaciones) - 5} más")
            
            # Mostrar total
            if 'importe_operacion' in operaciones[0]:
                total = sum(op.get('importe_operacion', 0) for op in operaciones)
            else:
                total = sum(op.get('importe', 0) for op in operaciones)
            
            st.write(f"   💰 **Total: {total:.2f}€**")

class GestorSesion:
    """Clase para manejar el estado de la sesión de Streamlit"""
    
    @staticmethod
    def inicializar_sesion():
        """Inicializa las variables de sesión necesarias"""
        if 'resultados_procesamiento' not in st.session_state:
            st.session_state.resultados_procesamiento = []
        if 'archivos_procesados' not in st.session_state:
            st.session_state.archivos_procesados = []
        if 'archivos_descargados' not in st.session_state:
            st.session_state.archivos_descargados = set()
        if 'debug_mode' not in st.session_state:
            st.session_state.debug_mode = False
    
    @staticmethod
    def reiniciar_aplicacion():
        """Reinicia completamente la aplicación limpiando todo el estado"""
        keys_to_clear = [
            'resultados_procesamiento',
            'archivos_procesados', 
            'archivos_descargados',
            'file_uploader_main'
        ]
        
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        st.rerun()
    
    @staticmethod
    def archivos_han_cambiado(archivos_actuales: List[str]) -> bool:
        """Verifica si los archivos han cambiado desde la última ejecución"""
        archivos_previos = st.session_state.get('archivos_procesados', [])
        return archivos_actuales != archivos_previos
    
    @staticmethod
    def marcar_archivo_descargado(nombre_archivo: str):
        """Marca un archivo como descargado"""
        if 'archivos_descargados' not in st.session_state:
            st.session_state.archivos_descargados = set()
        
        st.session_state.archivos_descargados.add(nombre_archivo)
    
    @staticmethod
    def archivo_fue_descargado(nombre_archivo: str) -> bool:
        """Verifica si un archivo ya fue descargado"""
        return nombre_archivo in st.session_state.get('archivos_descargados', set())

class ValidadorDatos:
    """Clase para validar y limpiar datos extraídos"""
    
    @staticmethod
    def validar_operacion_fraccionada(operacion: Dict) -> bool:
        """Valida que una operación fraccionada tenga los datos mínimos"""
        campos_requeridos = ['fecha', 'concepto', 'importe_operacion']
        
        for campo in campos_requeridos:
            if campo not in operacion or not operacion[campo]:
                return False
        
        # Validar formato de fecha
        if not re.match(r'\d{2}\.\d{2}\.\d{4}', operacion['fecha']):
            return False
        
        # Validar que el importe sea numérico
        try:
            float(operacion['importe_operacion'])
        except (ValueError, TypeError):
            return False
        
        return True
    
    @staticmethod
    def limpiar_operaciones(operaciones: List[Dict]) -> List[Dict]:
        """Limpia y valida una lista de operaciones"""
        operaciones_limpias = []
        
        for operacion in operaciones:
            if ValidadorDatos.validar_operacion_fraccionada(operacion):
                # Limpiar datos
                operacion_limpia = operacion.copy()
                
                # Asegurar que los importes sean numéricos
                campos_numericos = ['importe_operacion', 'importe_pendiente', 'capital_amortizado', 'intereses', 'cuota_mensual', 'importe_pendiente_despues']
                
                for campo in campos_numericos:
                    if campo in operacion_limpia:
                        try:
                            operacion_limpia[campo] = float(operacion_limpia[campo])
                        except (ValueError, TypeError):
                            operacion_limpia[campo] = 0.0
                
                operaciones_limpias.append(operacion_limpia)
        
        return operaciones_limpias

# Funciones principales que se importarán desde main.py
def crear_excel(info_general: Dict, operaciones_fraccionadas: List[Dict], operaciones_periodo: List[Dict]) -> bytes:
    """Función principal para crear archivos Excel"""
    generador = GeneradorExcel()
    return generador.crear_excel(info_general, operaciones_fraccionadas, operaciones_periodo)

def generar_nombre_archivo_excel(nombre_pdf: str) -> str:
    """Función principal para generar nombres de archivo Excel"""
    generador = GeneradorExcel()
    return generador.generar_nombre_archivo(nombre_pdf)

def mostrar_debug_completo(texto: str, pdf_id: str):
    """Función principal para mostrar debug completo"""
    debug = DebugHelper()
    debug.mostrar_estadisticas_texto(texto, pdf_id)
    debug.mostrar_muestra_texto(texto, pdf_id)
    debug.mostrar_menciones_banco(texto, "CAJ.LA CAIXA")

def reiniciar_aplicacion():
    """Función principal para reiniciar la aplicación"""
    GestorSesion.reiniciar_aplicacion()

def inicializar_sesion():
    """Función principal para inicializar la sesión"""
    GestorSesion.inicializar_sesion()

# Para testing independiente
if __name__ == "__main__":
    print("Módulo de utilidades - v2.6")
    print("Funciones disponibles:")
    print("- crear_excel()")
    print("- mostrar_debug_completo()")
    print("- reiniciar_aplicacion()")
    print("- inicializar_sesion()")
