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
                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if texto:
                        texto_completo += texto + "\n"
        except Exception as e:
            st.error(f"Error al leer el PDF: {str(e)}")
            return ""
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
    
    def extraer_operaciones_fraccionadas(self, texto: str) -> List[Dict]:
        """Extrae operaciones fraccionadas del texto"""
        operaciones = []
        
        # Debug: Mostrar fragmento del texto
        if st.session_state.get('debug_mode', False):
            st.text_area("🔍 Fragmento del texto extraído (primeros 2000 caracteres)", texto[:2000], height=200)
        
        # Buscar sección de operaciones fraccionadas
        patron_seccion = r'IMPORTE OPERACIONES FRACCIONADAS(.*?)(?=OPERACIONES DE LA TARJETA|TOTAL|Página|\n\s*\n|\Z)'
        match_seccion = re.search(patron_seccion, texto, re.DOTALL | re.IGNORECASE)
        
        if match_seccion:
            seccion_texto = match_seccion.group(1)
            
            if st.session_state.get('debug_mode', False):
                st.text_area("🔍 Sección de operaciones fraccionadas encontrada", seccion_texto[:1000], height=150)
            
            lineas = seccion_texto.split('\n')
            
            for i, linea in enumerate(lineas):
                linea = linea.strip()
                
                # Buscar líneas que contengan fecha y conceptos típicos de fraccionadas
                if re.search(r'\d{2}\.\d{2}\.\d{4}', linea):
                    # Dividir la línea por espacios y filtrar elementos vacíos
                    partes = [p for p in linea.split() if p.strip()]
                    
                    if len(partes) >= 3:
                        try:
                            fecha = partes[0]
                            
                            # Verificar que es una fecha válida
                            if not re.match(r'\d{2}\.\d{2}\.\d{4}', fecha):
                                continue
                            
                            # Buscar números (importes) en la línea
                            numeros = []
                            concepto_partes = []
                            
                            for parte in partes[1:]:
                                if re.match(r'\d+[,\.]\d{2}$', parte):
                                    # Es un número
                                    try:
                                        numeros.append(float(parte.replace(',', '.')))
                                    except ValueError:
                                        continue
                                else:
                                    # Parte del concepto
                                    concepto_partes.append(parte)
                            
                            # Si encontramos al menos 3 números, procesamos la operación
                            if len(numeros) >= 3:
                                concepto = ' '.join(concepto_partes)
                                
                                # Buscar información adicional en las siguientes líneas
                                plazo = ""
                                importe_pendiente_despues = 0.0
                                
                                # Revisar las siguientes 3 líneas para encontrar más información
                                for j in range(i+1, min(i+4, len(lineas))):
                                    linea_siguiente = lineas[j].strip()
                                    
                                    # Buscar plazo
                                    plazo_match = re.search(r'Plazo\s+(\d+\s+De\s+\d+)', linea_siguiente, re.IGNORECASE)
                                    if plazo_match:
                                        plazo = plazo_match.group(1)
                                    
                                    # Buscar "Importe pendiente después"
                                    if "Importe pendiente después" in linea_siguiente or "pendiente después" in linea_siguiente:
                                        # Buscar el siguiente número
                                        if j+1 < len(lineas):
                                            siguiente = lineas[j+1].strip()
                                            pendiente_match = re.search(r'(\d+[,\.]\d{2})', siguiente)
                                            if pendiente_match:
                                                try:
                                                    importe_pendiente_despues = float(pendiente_match.group(1).replace(',', '.'))
                                                except ValueError:
                                                    pass
                                
                                # Crear la operación con los datos disponibles
                                operacion = {
                                    'fecha': fecha,
                                    'concepto': concepto.strip() if concepto.strip() else 'Operación Fraccionada',
                                    'importe_operacion': numeros[0] if len(numeros) > 0 else 0.0,
                                    'importe_pendiente': numeros[1] if len(numeros) > 1 else 0.0,
                                    'capital_amortizado': numeros[2] if len(numeros) > 2 else 0.0,
                                    'intereses': numeros[3] if len(numeros) > 3 else 0.0,
                                    'cuota_mensual': numeros[4] if len(numeros) > 4 else 0.0,
                                    'plazo': plazo,
                                    'importe_pendiente_despues': importe_pendiente_despues
                                }
                                operaciones.append(operacion)
                                
                                if st.session_state.get('debug_mode', False):
                                    st.write(f"✅ Operación fraccionada encontrada: {fecha} - {concepto}")
                                
                        except (ValueError, IndexError) as e:
                            if st.session_state.get('debug_mode', False):
                                st.write(f"❌ Error procesando línea: {linea[:100]}... Error: {str(e)}")
                            continue
        
        if st.session_state.get('debug_mode', False):
            st.write(f"🔢 Total operaciones fraccionadas encontradas: {len(operaciones)}")
            if operaciones:
                st.write("📋 Primeras operaciones:")
                for i, op in enumerate(operaciones[:2]):
                    st.json(op)
        
        return operaciones
    
    def extraer_operaciones_periodo(self, texto: str) -> List[Dict]:
        """Extrae operaciones del período del texto"""
        operaciones = []
        
        # Buscar todas las líneas que parezcan operaciones
        lineas = texto.split('\n')
        
        for linea in lineas:
            linea = linea.strip()
            
            # Patrón mejorado para operaciones del período
            # Buscar: fecha + establecimiento + localidad + importe
            patron_operacion = r'^(\d{2}\.\d{2}\.\d{4})\s+([A-Z][A-Z\s\.\-&0-9,\(\)\']*?)\s+([A-Z][A-Z\s\-\']*?)\s+(\d+[,\.]\d{2})(?:\s|$)'
            
            match = re.match(patron_operacion, linea)
            if match:
                fecha = match.group(1)
                establecimiento = match.group(2).strip()
                localidad = match.group(3).strip()
                importe_str = match.group(4)
                
                try:
                    importe = float(importe_str.replace(',', '.'))
                    
                    # Filtrar líneas que puedan ser falsas coincidencias
                    if len(establecimiento) > 3 and len(localidad) > 2:
                        operacion = {
                            'fecha': fecha,
                            'establecimiento': establecimiento,
                            'localidad': localidad,
                            'importe': importe
                        }
                        operaciones.append(operacion)
                        
                        if st.session_state.get('debug_mode', False) and len(operaciones) <= 3:
                            st.write(f"✅ Operación del período: {fecha} - {establecimiento} - {importe}€")
                            
                except ValueError:
                    continue
        
        # Método alternativo: buscar en sección específica si no encontramos suficientes
        if len(operaciones) < 5:  # Si encontramos muy pocas, probar método alternativo
            if st.session_state.get('debug_mode', False):
                st.write(f"🔄 Solo se encontraron {len(operaciones)} operaciones, probando método alternativo...")
            
            # Buscar sección de operaciones de la tarjeta
            patron_seccion = r'OPERACIONES DE LA TARJETA.*?(?=Página|\n\s*\n|\Z)'
            matches_seccion = re.finditer(patron_seccion, texto, re.DOTALL | re.IGNORECASE)
            
            for match_seccion in matches_seccion:
                seccion_texto = match_seccion.group(0)
                lineas_seccion = seccion_texto.split('\n')
                
                for linea in lineas_seccion:
                    linea = linea.strip()
                    
                    # Buscar líneas con fechas
                    if re.match(r'^\d{2}\.\d{2}\.\d{4}', linea):
                        # Dividir la línea y buscar el patrón
                        partes = linea.split()
                        if len(partes) >= 4:
                            try:
                                fecha = partes[0]
                                # El importe suele estar al final
                                importe_candidatos = [p for p in partes if re.match(r'^\d+[,\.]\d{2}$', p)]
                                
                                if importe_candidatos:
                                    importe = float(importe_candidatos[-1].replace(',', '.'))
                                    
                                    # Encontrar establecimiento y localidad
                                    partes_sin_fecha_importe = partes[1:-1] if importe_candidatos else partes[1:]
                                    
                                    # Intentar separar establecimiento de localidad
                                    if len(partes_sin_fecha_importe) >= 2:
                                        # Heurística: la localidad suele ser más corta y al final
                                        punto_corte = len(partes_sin_fecha_importe) // 2
                                        establecimiento = ' '.join(partes_sin_fecha_importe[:punto_corte])
                                        localidad = ' '.join(partes_sin_fecha_importe[punto_corte:])
                                        
                                        # Verificar que no sea duplicado
                                        operacion_nueva = {
                                            'fecha': fecha,
                                            'establecimiento': establecimiento.strip(),
                                            'localidad': localidad.strip(),
                                            'importe': importe
                                        }
                                        
                                        # Evitar duplicados
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
            st.write(f"🔢 Total operaciones del período encontradas: {len(operaciones)}")
        
        return operaciones
    
    def procesar_pdf(self, archivo_pdf) -> Tuple[Dict, List[Dict], List[Dict]]:
        """Procesa el PDF completo y extrae toda la información"""
        texto = self.extraer_texto_pdf(archivo_pdf)
        
        if not texto:
            return {}, [], []
        
        info_general = self.extraer_informacion_general(texto)
        operaciones_fraccionadas = self.extraer_operaciones_fraccionadas(texto)
        operaciones_periodo = self.extraer_operaciones_periodo(texto)
        
        return info_general, operaciones_fraccionadas, operaciones_periodo

def crear_excel(info_general: Dict, operaciones_fraccionadas: List[Dict], operaciones_periodo: List[Dict]) -> bytes:
    """Crea un archivo Excel con los datos extraídos"""
    
    # Crear buffer en memoria
    buffer = io.BytesIO()
    
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # Hoja de resumen
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
        
        # Hoja de operaciones fraccionadas
        if operaciones_fraccionadas:
            df_fraccionadas = pd.DataFrame(operaciones_fraccionadas)
            df_fraccionadas.to_excel(writer, sheet_name='Operaciones Fraccionadas', index=False)
        
        # Hoja de operaciones del período
        if operaciones_periodo:
            df_periodo = pd.DataFrame(operaciones_periodo)
            df_periodo.to_excel(writer, sheet_name='Operaciones Período', index=False)
    
    buffer.seek(0)
    return buffer.getvalue()

def main():
    st.title("📊 Convertidor de Extractos Bancarios PDF a Excel v1.3")
    st.markdown("---")
    
    # Checkbox para modo debug
    debug_mode = st.sidebar.checkbox("🔍 Modo Debug", help="Muestra información adicional para diagnóstico")
    if 'debug_mode' not in st.session_state:
        st.session_state['debug_mode'] = False
    st.session_state['debug_mode'] = debug_mode
    
    # Información de la aplicación
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
        """)
    
    # Subida de archivo
    archivo_pdf = st.file_uploader(
        "📁 Selecciona el archivo PDF del extracto bancario",
        type=['pdf'],
        help="Sube un archivo PDF de tu extracto bancario"
    )
    
    if archivo_pdf is not None:
        st.success(f"✅ Archivo cargado: {archivo_pdf.name}")
        
        # Botón para procesar
        if st.button("🔄 Procesar PDF", type="primary"):
            with st.spinner("Procesando archivo PDF..."):
                # Inicializar extractor
                extractor = ExtractorExtractoBancario()
                
                # Procesar PDF
                info_general, operaciones_fraccionadas, operaciones_periodo = extractor.procesar_pdf(archivo_pdf)
                
                # Debug: Mostrar información de depuración
                if debug_mode:
                    st.subheader("🔍 Información de Debug")
                    st.write(f"Operaciones fraccionadas encontradas: {len(operaciones_fraccionadas)}")
                    st.write(f"Operaciones del período encontradas: {len(operaciones_periodo)}")
                    
                    if operaciones_fraccionadas:
                        st.write("Primeras operaciones fraccionadas:")
                        st.json(operaciones_fraccionadas[:2])
                
                # Mostrar resultados
                if info_general or operaciones_fraccionadas or operaciones_periodo:
                    st.success("✅ PDF procesado exitosamente")
                    
                    # Mostrar información general
                    if info_general:
                        st.subheader("📋 Información General")
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            if 'titular' in info_general:
                                st.metric("Titular", info_general['titular'])
                        
                        with col2:
                            if 'periodo_inicio' in info_general and 'periodo_fin' in info_general:
                                st.metric("Período", f"{info_general['periodo_inicio']} - {info_general['periodo_fin']}")
                        
                        with col3:
                            if 'limite_credito' in info_general:
                                st.metric("Límite de Crédito", f"{info_general['limite_credito']} €")
                    
                    # Estadísticas
                    st.subheader("📊 Estadísticas")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Operaciones Fraccionadas", len(operaciones_fraccionadas))
                    
                    with col2:
                        st.metric("Operaciones del Período", len(operaciones_periodo))
                    
                    with col3:
                        if operaciones_fraccionadas:
                            total_fraccionadas = sum(op.get('importe_operacion', 0) for op in operaciones_fraccionadas)
                            st.metric("Total Fraccionadas", f"{total_fraccionadas:.2f} €")
                    
                    with col4:
                        if operaciones_periodo:
                            total_periodo = sum(op.get('importe', 0) for op in operaciones_periodo)
                            st.metric("Total Período", f"{total_periodo:.2f} €")
                    
                    # Mostrar datos en tablas
                    if operaciones_fraccionadas:
                        st.subheader("💳 Operaciones Fraccionadas")
                        df_fraccionadas = pd.DataFrame(operaciones_fraccionadas)
                        st.dataframe(df_fraccionadas, use_container_width=True)
                    else:
                        st.warning("⚠️ No se encontraron operaciones fraccionadas en el PDF")
                    
                    if operaciones_periodo:
                        st.subheader("🛒 Operaciones del Período")
                        df_periodo = pd.DataFrame(operaciones_periodo)
                        st.dataframe(df_periodo, use_container_width=True)
                    else:
                        st.warning("⚠️ No se encontraron operaciones del período en el PDF")
                    
                    # Generar Excel
                    st.subheader("📥 Descargar Excel")
                    
                    try:
                        excel_data = crear_excel(info_general, operaciones_fraccionadas, operaciones_periodo)
                        
                        # Nombre del archivo
                        fecha_actual = datetime.now().strftime("%Y%m%d_%H%M%S")
                        nombre_archivo = f"extracto_bancario_{fecha_actual}.xlsx"
                        
                        # Botón de descarga
                        st.download_button(
                            label="📊 Descargar archivo Excel",
                            data=excel_data,
                            file_name=nombre_archivo,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                        
                        st.success("✅ Archivo Excel generado correctamente")
                        
                    except Exception as e:
                        st.error(f"❌ Error al generar el archivo Excel: {str(e)}")
                
                else:
                    st.warning("⚠️ No se pudo extraer información del PDF. Verifique que el formato sea correcto.")
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666; font-size: 0.8em;'>
        Convertidor de Extractos Bancarios v1.3 | Desarrollado para Streamlit por ROF
        </div>
        """, 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
