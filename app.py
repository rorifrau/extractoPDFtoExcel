import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime
import io
import base64
from typing import Dict, List, Tuple, Optional

# Configuración de la página
st.set_page_config(
    page_title="Convertidor de Extractos Bancarios",
    page_icon="📊",
    layout="wide"
)

class ExtractorExtractoBancario:
    def __init__(self):
        self.patrones = {
            'fecha': r'\d{2}\.\d{2}\.\d{4}',
            'importe': r'\d+[,\.]\d{2}',
            'operacion_fraccionada': r'(CAJ\.LA CAIXA|CAJERO|B\.B\.V\.A|FRACCIONADO)',
            'establecimiento': r'^[A-Z][A-Z\s\.\-&0-9]*$'
        }
    
    def extraer_texto_pdf(self, archivo_pdf) -> str:
        """Extrae texto del PDF usando pdfplumber"""
        texto_completo = ""
        try:
            with pdfplumber.open(archivo_pdf) as pdf:
                if st.session_state.get('debug_mode', False):
                    st.write(f"📄 PDF tiene {len(pdf.pages)} páginas")
                
                for i, pagina in enumerate(pdf.pages):
                    texto = pagina.extract_text()
                    if texto:
                        texto_completo += texto + "\n"
                        if st.session_state.get('debug_mode', False):
                            st.write(f"📄 Página {i+1}: {len(texto)} caracteres extraídos")
                    else:
                        if st.session_state.get('debug_mode', False):
                            st.write(f"⚠️ Página {i+1}: No se pudo extraer texto")
                            
        except Exception as e:
            st.error(f"Error al leer el PDF: {str(e)}")
            return ""
        
        if st.session_state.get('debug_mode', False):
            st.write(f"📊 Texto total extraído: {len(texto_completo)} caracteres")
        
        return texto_completo
    
    def extraer_informacion_general(self, texto: str) -> Dict:
        """Extrae información general del extracto"""
        info = {}
        
        # Buscar titular
        patron_titular = r'([A-Z\s]+)\s+\d{5}-\d{2}'
        match_titular = re.search(patron_titular, texto)
        if match_titular:
            info['titular'] = match_titular.group(1).strip()
        
        # Buscar período
        patron_periodo = r'(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})'
        match_periodo = re.search(patron_periodo, texto)
        if match_periodo:
            info['periodo_inicio'] = match_periodo.group(1)
            info['periodo_fin'] = match_periodo.group(2)
        
        # Buscar límite de crédito
        patron_limite = r'LÍMITE.*?(\d+[,\.]\d{2})'
        match_limite = re.search(patron_limite, texto, re.IGNORECASE)
        if match_limite:
            info['limite_credito'] = match_limite.group(1).replace(',', '.')
        
        return info
    
    def extraer_operaciones_fraccionadas(self, texto: str, pdf_id: str = "default") -> List[Dict]:
        """Extrae operaciones fraccionadas con métodos mejorados"""
        operaciones = []
        
        if st.session_state.get('debug_mode', False):
            st.write(f"🔍 **DEBUG DETALLADO para PDF: {pdf_id}**")
            st.write(f"📄 Longitud del texto extraído: {len(texto)} caracteres")
            
            if len(texto) > 0:
                st.text_area("🔍 Texto extraído (primeros 4000 caracteres)", 
                            texto[:4000], height=300, key=f"debug_texto_{pdf_id}")
                
                menciones_caixa = re.findall(r'.*CAJ\.LA CAIXA.*', texto, re.IGNORECASE)
                st.write(f"🔍 Menciones de 'CAJ.LA CAIXA': {len(menciones_caixa)}")
                for i, mencion in enumerate(menciones_caixa[:15]):
                    st.write(f"   {i+1}. {mencion}")
                
                fechas = re.findall(r'\d{2}\.\d{2}\.\d{4}', texto)
                st.write(f"🔍 Fechas encontradas: {len(fechas)} -> {fechas[:15]}")
                
                numeros = re.findall(r'\d+[,\.]\d{2}', texto)
                st.write(f"🔍 Números decimales: {len(numeros)} -> {numeros[:20]}")
        
        # MÉTODO 1: Buscar sección específica de operaciones fraccionadas
        seccion_match = re.search(r'IMPORTE OPERACIONES FRACCIONADAS(.*?)(?=OPERACIONES DE LA TARJETA|$)', texto, re.DOTALL | re.IGNORECASE)
        
        if seccion_match:
            seccion_texto = seccion_match.group(1)
            if st.session_state.get('debug_mode', False):
                st.write(f"📋 Sección fraccionadas encontrada: {len(seccion_texto)} caracteres")
                st.text_area("Sección completa", seccion_texto, height=300, key=f"seccion_{pdf_id}")
            
            # Patrón para formato tabla CaixaBank: FECHA CAJ.LA CAIXA OF.XXXX IMPORTE1 IMPORTE2 CAPITAL INTERESES CUOTA
            patron_tabla = r'(\d{2}\.\d{2}\.\d{4})\s+CAJ\.LA\s*CAIXA\s+(?:OF\.\d{4})?\s*(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})'
            
            matches = re.finditer(patron_tabla, seccion_texto, re.IGNORECASE)
            
            for match in matches:
                try:
                    fecha = match.group(1)
                    importe_operacion = float(match.group(2).replace(',', '.'))
                    importe_pendiente = float(match.group(3).replace(',', '.'))
                    capital_amortizado = float(match.group(4).replace(',', '.'))
                    intereses = float(match.group(5).replace(',', '.'))
                    cuota_mensual = float(match.group(6).replace(',', '.'))
                    
                    # Buscar plazo en contexto
                    plazo = ""
                    importe_pendiente_despues = 0.0
                    
                    inicio_contexto = max(0, match.start() - 50)
                    fin_contexto = min(len(seccion_texto), match.end() + 200)
                    contexto = seccion_texto[inicio_contexto:fin_contexto]
                    
                    plazo_match = re.search(r'Plazo\s+(\d+\s*De\s*\d+)', contexto, re.IGNORECASE)
                    if not plazo_match:
                        plazo_match = re.search(r'PRÓXIMO\s*PLAZO\s*(\d{2}-\d{2}-\d{4})', contexto, re.IGNORECASE)
                    if plazo_match:
                        plazo = plazo_match.group(1)
                    
                    pendiente_match = re.search(r'Importe\s+pendiente\s+después.*?(\d+[,\.]\d{2})', contexto, re.IGNORECASE)
                    if pendiente_match:
                        try:
                            importe_pendiente_despues = float(pendiente_match.group(1).replace(',', '.'))
                        except ValueError:
                            pass
                    
                    operacion = {
                        'fecha': fecha,
                        'concepto': 'CAJ.LA CAIXA',
                        'importe_operacion': importe_operacion,
                        'importe_pendiente': importe_pendiente,
                        'capital_amortizado': capital_amortizado,
                        'intereses': intereses,
                        'cuota_mensual': cuota_mensual,
                        'plazo': plazo,
                        'importe_pendiente_despues': importe_pendiente_despues
                    }
                    operaciones.append(operacion)
                    
                    if st.session_state.get('debug_mode', False):
                        st.write(f"✅ Método tabla: {fecha} - {importe_operacion}€ - Plazo: {plazo}")
                
                except Exception as e:
                    if st.session_state.get('debug_mode', False):
                        st.write(f"❌ Error método tabla: {str(e)}")
                    continue
        
        # MÉTODO 2: Buscar línea por línea si no encontramos suficientes
        if len(operaciones) < 5:
            if st.session_state.get('debug_mode', False):
                st.write(f"🔄 Método tabla: {len(operaciones)} operaciones. Probando línea por línea...")
            
            lineas = texto.split('\n')
            for i, linea in enumerate(lineas):
                linea = linea.strip()
                
                if re.match(r'^\d{2}\.\d{2}\.\d{4}', linea) and 'CAJ.LA CAIXA' in linea.upper():
                    if st.session_state.get('debug_mode', False):
                        st.write(f"🔍 Línea candidata {i+1}: {linea}")
                    
                    try:
                        partes = linea.split()
                        fecha = partes[0]
                        numeros = re.findall(r'\d+[,\.]\d{2}', linea)
                        
                        if st.session_state.get('debug_mode', False):
                            st.write(f"   📅 Fecha: {fecha}, 💰 Números: {numeros}")
                        
                        if len(numeros) >= 1:
                            numeros_float = [float(n.replace(',', '.')) for n in numeros]
                            
                            plazo = ""
                            importe_pendiente_despues = 0.0
                            
                            for j in range(i+1, min(i+6, len(lineas))):
                                linea_siguiente = lineas[j].strip()
                                
                                plazo_match = re.search(r'Plazo\s+(\d+\s*De\s*\d+)', linea_siguiente, re.IGNORECASE)
                                if not plazo_match:
                                    plazo_match = re.search(r'PRÓXIMO\s*PLAZO\s*(\d{2}-\d{2}-\d{4})', linea_siguiente, re.IGNORECASE)
                                if plazo_match:
                                    plazo = plazo_match.group(1)
                                
                                if "pendiente después" in linea_siguiente.lower():
                                    pendiente_match = re.search(r'(\d+[,\.]\d{2})', linea_siguiente)
                                    if pendiente_match:
                                        try:
                                            importe_pendiente_despues = float(pendiente_match.group(1).replace(',', '.'))
                                        except ValueError:
                                            pass
                            
                            operacion = {
                                'fecha': fecha,
                                'concepto': 'CAJ.LA CAIXA',
                                'importe_operacion': numeros_float[0],
                                'importe_pendiente': numeros_float[1] if len(numeros_float) > 1 else numeros_float[0],
                                'capital_amortizado': numeros_float[2] if len(numeros_float) > 2 else 0.0,
                                'intereses': numeros_float[3] if len(numeros_float) > 3 else 0.0,
                                'cuota_mensual': numeros_float[4] if len(numeros_float) > 4 else 0.0,
                                'plazo': plazo,
                                'importe_pendiente_despues': importe_pendiente_despues
                            }
                            
                            es_duplicado = any(
                                op['fecha'] == fecha and abs(op['importe_operacion'] - numeros_float[0]) < 0.01
                                for op in operaciones
                            )
                            
                            if not es_duplicado:
                                operaciones.append(operacion)
                                if st.session_state.get('debug_mode', False):
                                    st.write(f"✅ Método línea: {fecha} - {numeros_float[0]}€")
                    
                    except Exception as e:
                        if st.session_state.get('debug_mode', False):
                            st.write(f"❌ Error línea {i+1}: {str(e)}")
                        continue
        
        # MÉTODO 3: Patrón simple de respaldo
        if len(operaciones) == 0:
            if st.session_state.get('debug_mode', False):
                st.write("🔄 Probando método de respaldo...")
            
            patron_simple = r'(\d{2}\.\d{2}\.\d{4}).*?CAJ\.LA\s*CAIXA.*?(\d+[,\.]\d{2})'
            matches = re.finditer(patron_simple, texto, re.IGNORECASE | re.DOTALL)
            
            for match in matches:
                try:
                    fecha = match.group(1)
                    importe_str = match.group(2)
                    importe = float(importe_str.replace(',', '.'))
                    
                    operacion = {
                        'fecha': fecha,
                        'concepto': 'CAJ.LA CAIXA',
                        'importe_operacion': importe,
                        'importe_pendiente': importe,
                        'capital_amortizado': 0.0,
                        'intereses': 0.0,
                        'cuota_mensual': 0.0,
                        'plazo': '',
                        'importe_pendiente_despues': 0.0
                    }
                    
                    es_duplicado = any(
                        op['fecha'] == fecha and abs(op['importe_operacion'] - importe) < 0.01
                        for op in operaciones
                    )
                    
                    if not es_duplicado:
                        operaciones.append(operacion)
                        if st.session_state.get('debug_mode', False):
                            st.write(f"✅ Método respaldo: {fecha} - {importe}€")
                
                except Exception as e:
                    if st.session_state.get('debug_mode', False):
                        st.write(f"❌ Error respaldo: {str(e)}")
                    continue
        
        if st.session_state.get('debug_mode', False):
            st.write(f"🔢 **RESUMEN FINAL:**")
            st.write(f"   Total operaciones fraccionadas: {len(operaciones)}")
            if operaciones:
                st.write("📋 **Todas las operaciones:**")
                for i, op in enumerate(operaciones):
                    st.write(f"   {i+1}. {op['fecha']} - {op['concepto']} - {op['importe_operacion']}€ - Plazo: {op['plazo']}")
            else:
                st.error("❌ **NO SE ENCONTRARON OPERACIONES FRACCIONADAS**")
        
        return operaciones
    
    def extraer_operaciones_periodo(self, texto: str) -> List[Dict]:
        """Extrae operaciones del período del texto"""
        operaciones = []
        
        lineas = texto.split('\n')
        
        for linea in lineas:
            linea = linea.strip()
            
            patron_operacion = r'^(\d{2}\.\d{2}\.\d{4})\s+([A-Z][A-Z\s\.\-&0-9,\(\)\']*?)\s+([A-Z][A-Z\s\-\']*?)\s+(\d+[,\.]\d{2})(?:\s|$)'
            
            match = re.match(patron_operacion, linea)
            if match:
                fecha = match.group(1)
                establecimiento = match.group(2).strip()
                localidad = match.group(3).strip()
                importe_str = match.group(4)
                
                try:
                    importe = float(importe_str.replace(',', '.'))
                    
                    if len(establecimiento) > 3 and len(localidad) > 2:
                        operacion = {
                            'fecha': fecha,
                            'establecimiento': establecimiento,
                            'localidad': localidad,
                            'importe': importe
                        }
                        operaciones.append(operacion)
                        
                        if st.session_state.get('debug_mode', False) and len(operaciones) <= 3:
                            st.write(f"✅ Operación período: {fecha} - {establecimiento} - {importe}€")
                            
                except ValueError:
                    continue
        
        if len(operaciones) < 5:
            if st.session_state.get('debug_mode', False):
                st.write(f"🔄 Solo {len(operaciones)} operaciones período, probando método alternativo...")
            
            patron_seccion = r'OPERACIONES DE LA TARJETA.*?(?=Página|\n\s*\n|\Z)'
            matches_seccion = re.finditer(patron_seccion, texto, re.DOTALL | re.IGNORECASE)
            
            for match_seccion in matches_seccion:
                seccion_texto = match_seccion.group(0)
                lineas_seccion = seccion_texto.split('\n')
                
                for linea in lineas_seccion:
                    linea = linea.strip()
                    
                    if re.match(r'^\d{2}\.\d{2}\.\d{4}', linea):
                        partes = linea.split()
                        if len(partes) >= 4:
                            try:
                                fecha = partes[0]
                                patron_numerico = r'^\d+[,\.]\d{2}$'
                                importe_candidatos = [p for p in partes if re.match(patron_numerico, p)]
                                
                                if importe_candidatos:
                                    importe = float(importe_candidatos[-1].replace(',', '.'))
                                    
                                    partes_sin_fecha_importe = partes[1:-1] if importe_candidatos else partes[1:]
                                    
                                    if len(partes_sin_fecha_importe) >= 2:
                                        punto_corte = len(partes_sin_fecha_importe) // 2
                                        establecimiento = ' '.join(partes_sin_fecha_importe[:punto_corte])
                                        localidad = ' '.join(partes_sin_fecha_importe[punto_corte:])
                                        
                                        operacion_nueva = {
                                            'fecha': fecha,
                                            'establecimiento': establecimiento.strip(),
                                            'localidad': localidad.strip(),
                                            'importe': importe
                                        }
                                        
                                        es_duplicado = any(
                                            op['fecha'] == fecha and 
                                            op['establecimiento'] == establecimiento.strip() and 
                                            abs(op['importe'] - importe) < 0.01
                                            for op in operaciones
                                        )
                                        
                                        if not es_duplicado:
                                            operaciones.append(operacion_nueva)
                                        
                            except (ValueError, IndexError):
                                continue
        
        if st.session_state.get('debug_mode', False):
            st.write(f"🔢 Total operaciones del período: {len(operaciones)}")
        
        return operaciones
    
    def procesar_pdf(self, archivo_pdf) -> Tuple[Dict, List[Dict], List[Dict]]:
        """Procesa el PDF completo y extrae toda la información"""
        texto = self.extraer_texto_pdf(archivo_pdf)
        
        if not texto:
            return {}, [], []
        
        pdf_id = archivo_pdf.name.replace('.pdf', '').replace('.PDF', '').replace(' ', '_').replace('-', '_')
        
        info_general = self.extraer_informacion_general(texto)
        operaciones_fraccionadas = self.extraer_operaciones_fraccionadas(texto, pdf_id)
        operaciones_periodo = self.extraer_operaciones_periodo(texto)
        
        return info_general, operaciones_fraccionadas, operaciones_periodo

def crear_excel(info_general: Dict, operaciones_fraccionadas: List[Dict], operaciones_periodo: List[Dict]) -> bytes:
    """Crea un archivo Excel con los datos extraídos"""
    
    buffer = io.BytesIO()
    
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        resumen_data = []
        resumen_data.append(['EXTRACTO BANCARIO MYCARD'])
        resumen_data.append([''])
        
        if 'periodo_inicio' in info_general and 'periodo_fin' in info_general:
            resumen_data.append(['Período', f"{info_general['periodo_inicio']} - {info_general['periodo_fin']}"])
        
        if 'titular' in info_general:
            resumen_data.append(['Titular', info_general['titular']])
        
        if 'limite_credito' in info_general:
            resumen_data.append(['Límite de crédito', f"{info_general['limite_credito']} €"])
        
        resumen_data.append([''])
        resumen_data.append(['RESUMEN'])
        resumen_data.append(['Operaciones Fraccionadas', len(operaciones_fraccionadas)])
        resumen_data.append(['Operaciones del Período', len(operaciones_periodo)])
        
        if operaciones_fraccionadas:
            total_fraccionadas = sum(op.get('importe_operacion', 0) for op in operaciones_fraccionadas)
            resumen_data.append(['Total Fraccionadas', f"{total_fraccionadas:.2f} €"])
        
        if operaciones_periodo:
            total_periodo = sum(op.get('importe', 0) for op in operaciones_periodo)
            resumen_data.append(['Total Período', f"{total_periodo:.2f} €"])
        
        df_resumen = pd.DataFrame(resumen_data)
        df_resumen.to_excel(writer, sheet_name='Resumen', index=False, header=False)
        
        if operaciones_fraccionadas:
            df_fraccionadas = pd.DataFrame(operaciones_fraccionadas)
            df_fraccionadas.to_excel(writer, sheet_name='Operaciones Fraccionadas', index=False)
        
        if operaciones_periodo:
            df_periodo = pd.DataFrame(operaciones_periodo)
            df_periodo.to_excel(writer, sheet_name='Operaciones Período', index=False)
    
    buffer.seek(0)
    return buffer.getvalue()

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

def main():
    st.title("📊 Convertidor de Extractos Bancarios PDF a Excel v2.5")
    st.markdown("---")
    
    # Inicializar session_state
    if 'resultados_procesamiento' not in st.session_state:
        st.session_state.resultados_procesamiento = []
    if 'archivos_procesados' not in st.session_state:
        st.session_state.archivos_procesados = []
    if 'archivos_descargados' not in st.session_state:
        st.session_state.archivos_descargados = set()
    
    debug_mode = st.sidebar.checkbox("🔍 Modo Debug", help="Muestra información detallada para diagnóstico")
    if 'debug_mode' not in st.session_state:
        st.session_state['debug_mode'] = False
    st.session_state['debug_mode'] = debug_mode
    
    with st.expander("ℹ️ Información de la aplicación"):
        st.markdown("""
        Esta aplicación permite convertir extractos bancarios en formato PDF a archivos Excel organizados.
        
        **Características:**
        - Extrae información general (titular, período, límite de crédito)
        - Procesa operaciones fraccionadas (BBVA, CaixaBank, etc.)
        - Procesa operaciones del período
        - Genera un archivo Excel con múltiples hojas
        
        **Formatos soportados:**
        - Extractos bancarios MyCard de CaixaBank
        - Extractos de BBVA
        - PDFs con estructura similar
        
        **Versión 2.5** - Debug ultra-detallado, descarga mejorada, limpiar funcional
        """)
    
    # Botón de limpiar todo en la parte superior
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🗑️ Limpiar Todo", type="secondary", help="Reinicia completamente la aplicación"):
            reiniciar_aplicacion()
    
    archivos_pdf = st.file_uploader(
        "📁 Selecciona uno o varios archivos PDF de extractos bancarios",
        type=['pdf'],
        help="Sube uno o múltiples archivos PDF de tus extractos bancarios",
        accept_multiple_files=True,
        key="file_uploader_main"
    )
    
    # Verificar si los archivos han cambiado
    archivos_actuales = [pdf.name for pdf in archivos_pdf] if archivos_pdf else []
    if archivos_actuales != st.session_state.archivos_procesados:
        st.session_state.resultados_procesamiento = []
        st.session_state.archivos_procesados = archivos_actuales
        st.session_state.archivos_descargados = set()
    
    if archivos_pdf is not None and len(archivos_pdf) > 0:
        st.success(f"✅ {len(archivos_pdf)} archivo(s) cargado(s):")
        for i, pdf in enumerate(archivos_pdf, 1):
            st.write(f"   {i}. {pdf.name}")
        
        # Botón para procesar
        if len(st.session_state.resultados_procesamiento) == 0:
            if st.button("🔄 Procesar todos los PDFs", type="primary"):
                resultados = []
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, pdf in enumerate(archivos_pdf):
                    progress = (i + 1) / len(archivos_pdf)
                    progress_bar.progress(progress)
                    status_text.text(f"Procesando {pdf.name} ({i+1}/{len(archivos_pdf)})...")
                    
                    try:
                        with st.spinner(f"Procesando {pdf.name}..."):
                            extractor = ExtractorExtractoBancario()
                            info_general, operaciones_fraccionadas, operaciones_periodo = extractor.procesar_pdf(pdf)
                            
                            excel_data = crear_excel(info_general, operaciones_fraccionadas, operaciones_periodo)
                            
                            nombre_archivo = "extractoTarjeta.xlsx"
                            if pdf.name:
                                fecha_match = re.match(r'^(\d{1,2}\s+\w{3}\s+\d{4})', pdf.name)
                                if fecha_match:
                                    fecha_extraida = fecha_match.group(1)
                                    nombre_archivo = f"{fecha_extraida}_extractoTarjeta.xlsx"
                                else:
                                    fecha_match2 = re.search(r'(\d{1,2})\s*(\w{3})\s*(\d{4})', pdf.name)
                                    if fecha_match2:
                                        dia = fecha_match2.group(1)
                                        mes = fecha_match2.group(2)
                                        año = fecha_match2.group(3)
                                        nombre_archivo = f"{dia} {mes} {año}_extractoTarjeta.xlsx"
                                    else:
                                        nombre_base = pdf.name.replace('.pdf', '').replace('.PDF', '')
                                        nombre_archivo = f"{nombre_base}_extractoTarjeta.xlsx"
                            
                            resultado = {
                                'nombre_pdf': pdf.name,
                                'estado': 'success',
                                'info_general': info_general,
                                'operaciones_fraccionadas': operaciones_fraccionadas,
                                'operaciones_periodo': operaciones_periodo,
                                'excel_data': excel_data,
                                'nombre_excel': nombre_archivo
                            }
                            
                    except Exception as e:
                        resultado = {
                            'nombre_pdf': pdf.name,
                            'estado': 'error',
                            'error': str(e),
                            'info_general': {},
                            'operaciones_fraccionadas': [],
                            'operaciones_periodo': [],
                            'excel_data': None,
                            'nombre_excel': None
                        }
                    
                    resultados.append(resultado)
                
                st.session_state.resultados_procesamiento = resultados
                progress_bar.empty()
                status_text.empty()
                st.rerun()
        
        # Mostrar resultados si existen
        if len(st.session_state.resultados_procesamiento) > 0:
            resultados = st.session_state.resultados_procesamiento
            
            if st.button("🔄 Procesar nuevamente", type="secondary"):
                st.session_state.resultados_procesamiento = []
                st.session_state.archivos_descargados = set()
                st.rerun()
            
            st.success(f"✅ Procesamiento completado de {len(archivos_pdf)} archivo(s)")
            
            exitosos = len([r for r in resultados if r['estado'] == 'success'])
            errores = len([r for r in resultados if r['estado'] == 'error'])
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("📊 Procesados exitosamente", exitosos)
            with col2:
                st.metric("❌ Con errores", errores)
            
            st.subheader("📋 Resultados por archivo")
            
            for resultado in resultados:
                if resultado['estado'] == 'success':
                    with st.container():
                        st.markdown(f"### ✅ {resultado['nombre_pdf']}")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            if 'titular' in resultado['info_general']:
                                st.write(f"**Titular:** {resultado['info_general']['titular']}")
                        
                        with col2:
                            if 'periodo_inicio' in resultado['info_general'] and 'periodo_fin' in resultado['info_general']:
                                st.write(f"**Período:** {resultado['info_general']['periodo_inicio']} - {resultado['info_general']['periodo_fin']}")
                        
                        with col3:
                            st.metric("Fraccionadas", len(resultado['operaciones_fraccionadas']))
                        
                        with col4:
                            st.metric("Del Período", len(resultado['operaciones_periodo']))
                        
                        if resultado['excel_data']:
                            archivo_descargado = resultado['nombre_pdf'] in st.session_state.archivos_descargados
                            
                            col_btn, col_status = st.columns([3, 1])
                            
                            with col_btn:
                                btn_style = "secondary" if archivo_descargado else "primary"
                                btn_text = f"📥 Descargar Excel - {resultado['nombre_excel']}"
                                
                                if st.download_button(
                                    label=btn_text,
                                    data=resultado['excel_data'],
                                    file_name=resultado['nombre_excel'],
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key=f"download_{resultado['nombre_pdf']}_{hash(resultado['nombre_pdf'])}",
                                    type=btn_style
                                ):
                                    st.session_state.archivos_descargados.add(resultado['nombre_pdf'])
                                    st.rerun()
                            
                            with col_status:
                                if archivo_descargado:
                                    st.success("✅ Descargado")
                        
                        if debug_mode:
                            with st.expander(f"🔍 Debug info para {resultado['nombre_pdf']}"):
                                st.json({
                                    'operaciones_fraccionadas': len(resultado['operaciones_fraccionadas']),
                                    'operaciones_periodo': len(resultado['operaciones_periodo']),
                                    'info_general': resultado['info_general']
                                })
                                
                                if resultado['operaciones_fraccionadas']:
                                    st.write("**Primeras operaciones fraccionadas:**")
                                    for i, op in enumerate(resultado['operaciones_fraccionadas'][:3]):
                                        st.json(op)
                        
                        st.markdown("---")
                
                else:  # Error
                    with st.container():
                        st.markdown(f"### ❌ {resultado['nombre_pdf']}")
                        st.error(f"Error al procesar: {resultado['error']}")
                        st.markdown("---")
    
    else:
        st.info("👆 Selecciona uno o más archivos PDF para comenzar")
    
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666; font-size: 0.8em;'>
        Convertidor de Extractos Bancarios v2.5 | Debug ultra-detallado | Descarga mejorada | Limpiar funcional | Desarrollado con Streamlit por ROF
        </div>
        """, 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
