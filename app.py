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
            'operacion_fraccionada': r'(CAJ\.LA CAIXA|CAJERO)',
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
        
        # Debug: Mostrar texto para ver qué encuentra
        if st.session_state.get('debug_mode', False):
            st.text_area("Texto completo del PDF (debug)", texto[:2000], height=200)
        
        # Buscar patrones específicos de operaciones fraccionadas
        # Patrón mejorado que busca líneas con fechas seguidas de CAJ.LA CAIXA
        lineas = texto.split('\n')
        
        for i, linea in enumerate(lineas):
            # Buscar líneas que contengan fecha y CAJ.LA CAIXA
            if re.search(r'\d{2}\.\d{2}\.\d{4}.*CAJ\.LA CAIXA', linea):
                # Extraer información de esta línea y las siguientes
                partes = linea.strip().split()
                
                if len(partes) >= 7:  # Fecha + concepto + varios números
                    try:
                        fecha = partes[0]
                        concepto = ' '.join([p for p in partes[1:] if not re.match(r'\d+[,\.]\d{2}', p)][:3])
                        
                        # Buscar números en la línea
                        numeros = [p.replace(',', '.') for p in partes if re.match(r'\d+[,\.]\d{2}', p)]
                        
                        if len(numeros) >= 5:
                            # Buscar información adicional en líneas siguientes
                            plazo = ""
                            importe_pendiente_despues = 0.0
                            
                            # Revisar las siguientes líneas para encontrar plazo e importe pendiente después
                            for j in range(i+1, min(i+4, len(lineas))):
                                if "Plazo" in lineas[j]:
                                    plazo_match = re.search(r'(\d+\s+De\s+\d+)', lineas[j])
                                    if plazo_match:
                                        plazo = plazo_match.group(1)
                                
                                if "Importe pendiente después" in lineas[j]:
                                    siguiente_linea = j + 1
                                    if siguiente_linea < len(lineas):
                                        pendiente_match = re.search(r'(\d+[,\.]\d{2})', lineas[siguiente_linea])
                                        if pendiente_match:
                                            importe_pendiente_despues = float(pendiente_match.group(1).replace(',', '.'))
                            
                            operacion = {
                                'fecha': fecha,
                                'concepto': concepto.strip(),
                                'importe_operacion': float(numeros[0]),
                                'importe_pendiente': float(numeros[1]),
                                'capital_amortizado': float(numeros[2]),
                                'intereses': float(numeros[3]),
                                'cuota_mensual': float(numeros[4]),
                                'plazo': plazo,
                                'importe_pendiente_despues': importe_pendiente_despues
                            }
                            operaciones.append(operacion)
                            
                    except (ValueError, IndexError) as e:
                        # Si hay error en la conversión, continuar con la siguiente línea
                        continue
        
        # Si no encontramos operaciones con el método anterior, intentar método alternativo
        if not operaciones:
            # Buscar sección específica de operaciones fraccionadas
            patron_seccion = r'IMPORTE OPERACIONES FRACCIONADAS(.*?)(?=OPERACIONES DE LA TARJETA|TOTAL OPERACIONES FRACCIONADAS|$)'
            match_seccion = re.search(patron_seccion, texto, re.DOTALL | re.IGNORECASE)
            
            if match_seccion:
                seccion_texto = match_seccion.group(1)
                
                # Patrón más flexible para operaciones fraccionadas
                patron_operacion = r'(\d{2}\.\d{2}\.\d{4})\s+(CAJ\.LA CAIXA[^0-9]*)\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})'
                
                matches = re.findall(patron_operacion, seccion_texto)
                
                for match in matches:
                    operacion = {
                        'fecha': match[0],
                        'concepto': match[1].strip(),
                        'importe_operacion': float(match[2].replace(',', '.')),
                        'importe_pendiente': float(match[3].replace(',', '.')),
                        'capital_amortizado': float(match[4].replace(',', '.')),
                        'intereses': float(match[5].replace(',', '.')),
                        'cuota_mensual': float(match[6].replace(',', '.')),
                        'plazo': '',
                        'importe_pendiente_despues': 0.0
                    }
                    operaciones.append(operacion)
        
        return operaciones
    
    def extraer_operaciones_periodo(self, texto: str) -> List[Dict]:
        """Extrae operaciones del período del texto"""
        operaciones = []
        
        # Buscar todas las líneas que parecen operaciones
        lineas = texto.split('\n')
        
        for linea in lineas:
            # Patrón para operaciones del período
            patron_operacion = r'(\d{2}\.\d{2}\.\d{4})\s+([A-Z][A-Z\s\.\-&0-9]*?)\s+([A-Z][A-Z\s\-]*?)\s+(\d+[,\.]\d{2})(?:\s|$)'
            
            match = re.match(patron_operacion, linea.strip())
            if match:
                operacion = {
                    'fecha': match.group(1),
                    'establecimiento': match.group(2).strip(),
                    'localidad': match.group(3).strip(),
                    'importe': float(match.group(4).replace(',', '.'))
                }
                operaciones.append(operacion)
        
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
            total_fraccionadas = sum(op['importe_operacion'] for op in operaciones_fraccionadas)
            resumen_data.append(['Total Fraccionadas', f"{total_fraccionadas:.2f} €"])
        
        if operaciones_periodo:
            total_periodo = sum(op['importe'] for op in operaciones_periodo)
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
    st.title("📊 Convertidor de Extractos Bancarios PDF a Excel")
    st.markdown("---")
    
    # Información de la aplicación
    with st.expander("ℹ️ Información de la aplicación"):
        st.markdown("""
        Esta aplicación permite convertir extractos bancarios en formato PDF a archivos Excel organizados.

        versión 1.1
        
        **Características:**
        - Extrae información general (titular, período, límite de crédito)
        - Procesa operaciones fraccionadas
        - Procesa operaciones del período
        - Genera un archivo Excel con múltiples hojas
        
        **Formatos soportados:**
        - Extractos bancarios MyCard de CaixaBank
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
                            total_fraccionadas = sum(op['importe_operacion'] for op in operaciones_fraccionadas)
                            st.metric("Total Fraccionadas", f"{total_fraccionadas:.2f} €")
                    
                    with col4:
                        if operaciones_periodo:
                            total_periodo = sum(op['importe'] for op in operaciones_periodo)
                            st.metric("Total Período", f"{total_periodo:.2f} €")
                    
                    # Mostrar datos en tablas
                    if operaciones_fraccionadas:
                        st.subheader("💳 Operaciones Fraccionadas")
                        df_fraccionadas = pd.DataFrame(operaciones_fraccionadas)
                        st.dataframe(df_fraccionadas, use_container_width=True)
                    
                    if operaciones_periodo:
                        st.subheader("🛒 Operaciones del Período")
                        df_periodo = pd.DataFrame(operaciones_periodo)
                        st.dataframe(df_periodo, use_container_width=True)
                    
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
        Convertidor de Extractos Bancarios v1.2 | Desarrollado para Streamlit por ROF
        </div>
        """, 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
