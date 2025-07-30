import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime
import io
from typing import Dict, List, Tuple

# Configuración de la página
st.set_page_config(
    page_title="Convertidor de Extractos Bancarios",
    page_icon="📊",
    layout="wide"
)

class ExtractorExtractoBancario:
    """
    Clase para extraer información de extractos bancarios en formato PDF.
    """
    def __init__(self):
        """Inicializa los patrones de expresiones regulares."""
        self.patrones = {
            'fecha': r'\d{2}\.\d{2}\.\d{4}',
            'importe': r'\d+[,\.]\d{2}',
            'operacion_fraccionada': r'(CAJ\.LA CAIXA|CAJERO|B\.B\.V\.A|FRACCIONADO)',
            'establecimiento': r'^[A-Z][A-Z\s\.\-&0-9]*$'
        }

    def extraer_texto_pdf(self, archivo_pdf) -> str:
        """Extrae texto del PDF usando pdfplumber."""
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
        """Extrae información general del extracto (titular, período, límite)."""
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
        """Extrae operaciones fraccionadas del texto usando varios métodos."""
        operaciones = []
        
        if st.session_state.get('debug_mode', False):
            st.text_area("🔍 Fragmento del texto para Op. Fraccionadas (2000 car.)", texto[:2000], height=200)

        # Método 1: Buscar operaciones en formato de líneas individuales (BBVA)
        lineas = texto.split('\n')
        i = 0
        while i < len(lineas):
            linea = lineas[i].strip()
            
            if re.search(r'^\d{2}\.\d{2}\.\d{4}.*(B\.B\.V\.A\.|CAJ\.LA CAIXA)', linea):
                try:
                    partes = linea.split()
                    fecha = partes[0]
                    
                    patron_numero_completo = r'^\d+[,\.]\d{2}$'
                    numeros = [float(p.replace(',', '.')) for p in partes[1:] if re.match(patron_numero_completo, p)]
                    
                    concepto_partes = [p for p in partes[1:] if not re.match(patron_numero_completo, p) and p not in ['B.B.V.A.', 'CAJ.LA', 'CAIXA', 'OF.7102', 'OF.7104']]
                    concepto = ' '.join(concepto_partes).strip()

                    if 'B.B.V.A.' in linea:
                        concepto = 'B.B.V.A.' if not concepto else concepto
                    elif 'CAJ.LA CAIXA' in linea:
                        concepto = 'CAJ.LA CAIXA' if not concepto else concepto
                    
                    plazo = ""
                    importe_pendiente_despues = 0.0
                    
                    # Buscar información en las líneas siguientes
                    for j in range(i + 1, min(i + 6, len(lineas))):
                        linea_siguiente = lineas[j].strip()
                        plazo_match = re.search(r'Plazo\s+(\d+\s*De\s*\d+)|PRÓXIMO\s*PLAZO\s*(\d{2}-\d{2}-\d{4})', linea_siguiente, re.IGNORECASE)
                        if plazo_match:
                            plazo = plazo_match.group(1) or plazo_match.group(2)
                        
                        if "Importe pendiente después" in linea_siguiente or "Importependientedespués" in linea_siguiente:
                            pendiente_match = re.search(r'(\d+[,\.]\d{2})', linea_siguiente)
                            if pendiente_match:
                                importe_pendiente_despues = float(pendiente_match.group(1).replace(',', '.'))
                    
                    if len(numeros) >= 1:
                        operacion = {
                            'fecha': fecha, 'concepto': concepto,
                            'importe_operacion': numeros[0] if len(numeros) > 0 else 0.0,
                            'importe_pendiente': numeros[1] if len(numeros) > 1 else 0.0,
                            'capital_amortizado': numeros[2] if len(numeros) > 2 else 0.0,
                            'intereses': numeros[3] if len(numeros) > 3 else 0.0,
                            'cuota_mensual': numeros[4] if len(numeros) > 4 else 0.0,
                            'plazo': plazo, 'importe_pendiente_despues': importe_pendiente_despues
                        }
                        operaciones.append(operacion)
                        if st.session_state.get('debug_mode', False):
                            st.write(f"✅ Op. fraccionada (método 1): {fecha} - {concepto}")
                
                except (ValueError, IndexError) as e:
                    if st.session_state.get('debug_mode', False):
                        st.write(f"❌ Error en método 1: {str(e)} en línea: '{linea}'")
            i += 1
        
        # Si no se encontraron operaciones, se podrían añadir más métodos aquí.

        if st.session_state.get('debug_mode', False):
            st.write(f"🔢 Total operaciones fraccionadas encontradas: {len(operaciones)}")
        
        return operaciones

    def extraer_operaciones_periodo(self, texto: str) -> List[Dict]:
        """Extrae operaciones del período del texto."""
        operaciones = []
        lineas = texto.split('\n')
        
        # Método 1: Patrón de regex principal
        patron_operacion = r'^(\d{2}\.\d{2}\.\d{4})\s+([A-Z][A-Z\s\.\-&0-9,\(\)\']*?)\s+([A-Z][A-Z\s\-\']*?)\s+(\d+[,\.]\d{2})(?:\s|$)'
        for linea in lineas:
            match = re.match(patron_operacion, linea.strip())
            if match:
                try:
                    importe_servicios = 0.0
                    if "Importe servicios" in linea or "servicios:" in linea:
                        servicios_match = re.search(r'servicios:?\s*(\d+[,\.]\d{2})', linea, re.IGNORECASE)
                        if servicios_match:
                            importe_servicios = float(servicios_match.group(1).replace(',', '.'))

                    operacion = {
                        'fecha': match.group(1),
                        'establecimiento': match.group(2).strip(),
                        'localidad': match.group(3).strip(),
                        'importe': float(match.group(4).replace(',', '.')),
                        'importe_servicios': importe_servicios
                    }
                    if len(operacion['establecimiento']) > 3 and len(operacion['localidad']) > 2:
                        operaciones.append(operacion)
                except (ValueError, IndexError):
                    continue

        # Método 2 (Alternativo): Si el primero falla, se analiza por secciones
        if len(operaciones) < 5:
            if st.session_state.get('debug_mode', False):
                st.write(f"🔄 Solo se encontraron {len(operaciones)} operaciones, probando método alternativo...")
            
            patron_seccion = r'OPERACIONES DE LA TARJETA.*?(?=Página|\n\s*\n|\Z)'
            matches_seccion = re.finditer(patron_seccion, texto, re.DOTALL | re.IGNORECASE)
            
            for match_seccion in matches_seccion:
                seccion_texto = match_seccion.group(0)
                lineas_seccion = seccion_texto.split('\n')
                
                for linea in lineas_seccion:
                    linea = linea.strip()
                    if re.match(r'^\d{2}\.\d{2}\.\d{4}', linea):
                        partes = linea.split()
                        if len(partes) >= 3: # Fecha, concepto y importe como mínimo
                            try:
                                fecha = partes[0]
                                patron_num = r'^\d+[,\.]\d{2}$' # CORREGIDO: comilla final y '$' añadido

                                importe_candidatos = [p for p in partes if re.match(patron_num, p)]
                                
                                if importe_candidatos:
                                    importe = float(importe_candidatos[-1].replace(',', '.'))
                                    
                                    # Lógica para separar establecimiento y localidad
                                    partes_sin_fecha_importe = partes[1:-1]
                                    if len(partes_sin_fecha_importe) >= 1:
                                        punto_corte = (len(partes_sin_fecha_importe) + 1) // 2
                                        establecimiento = ' '.join(partes_sin_fecha_importe[:punto_corte])
                                        localidad = ' '.join(partes_sin_fecha_importe[punto_corte:])
                                        
                                        importe_servicios = 0.0
                                        if "Importe servicios" in linea or "servicios:" in linea:
                                            servicios_match = re.search(r'servicios:?\s*(\d+[,\.]\d{2})', linea, re.IGNORECASE)
                                            if servicios_match:
                                                importe_servicios = float(servicios_match.group(1).replace(',', '.'))
                                        
                                        operacion_nueva = {
                                            'fecha': fecha,
                                            'establecimiento': establecimiento.strip(),
                                            'localidad': localidad.strip(),
                                            'importe': importe,
                                            'importe_servicios': importe_servicios
                                        }

                                        # Evitar duplicados del primer método
                                        es_duplicado = any(
                                            op['fecha'] == fecha and op['establecimiento'] == establecimiento.strip() and abs(op['importe'] - importe) < 0.01
                                            for op in operaciones
                                        )
                                        if not es_duplicado:
                                            operaciones.append(operacion_nueva)

                            except (ValueError, IndexError) as e:
                                if st.session_state.get('debug_mode', False):
                                    st.write(f"❌ Error en método alternativo: {e} en línea: '{linea}'")
                                continue
        
        if st.session_state.get('debug_mode', False):
            st.write(f"🔢 Total operaciones del período encontradas: {len(operaciones)}")
        
        return operaciones

    def procesar_pdf(self, archivo_pdf) -> Tuple[Dict, List[Dict], List[Dict]]:
        """Procesa el PDF completo y extrae toda la información."""
        texto = self.extraer_texto_pdf(archivo_pdf)
        if not texto:
            return {}, [], []
        
        info_general = self.extraer_informacion_general(texto)
        operaciones_fraccionadas = self.extraer_operaciones_fraccionadas(texto)
        operaciones_periodo = self.extraer_operaciones_periodo(texto)
        
        return info_general, operaciones_fraccionadas, operaciones_periodo

def crear_excel(info_general: Dict, operaciones_fraccionadas: List[Dict], operaciones_periodo: List[Dict]) -> bytes:
    """Crea un archivo Excel con los datos extraídos."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # Hoja de Resumen
        resumen_data = [['EXTRACTO BANCARIO MYCARD'], ['']]
        if 'periodo_inicio' in info_general and 'periodo_fin' in info_general:
            resumen_data.append(['Período', f"{info_general['periodo_inicio']} - {info_general['periodo_fin']}"])
        if 'titular' in info_general:
            resumen_data.append(['Titular', info_general['titular']])
        if 'limite_credito' in info_general:
            resumen_data.append(['Límite de crédito', f"{info_general['limite_credito']} €"])
        resumen_data.extend([
            [''], ['RESUMEN'],
            ['Operaciones Fraccionadas', len(operaciones_fraccionadas)],
            ['Operaciones del Período', len(operaciones_periodo)]
        ])
        if operaciones_fraccionadas:
            total_fraccionadas = sum(op.get('importe_operacion', 0) for op in operaciones_fraccionadas)
            resumen_data.append(['Total Fraccionadas', f"{total_fraccionadas:.2f} €"])
        if operaciones_periodo:
            total_periodo = sum(op.get('importe', 0) for op in operaciones_periodo)
            resumen_data.append(['Total Período', f"{total_periodo:.2f} €"])
        
        pd.DataFrame(resumen_data).to_excel(writer, sheet_name='Resumen', index=False, header=False)
        
        # Hojas de datos
        if operaciones_fraccionadas:
            pd.DataFrame(operaciones_fraccionadas).to_excel(writer, sheet_name='Operaciones Fraccionadas', index=False)
        if operaciones_periodo:
            pd.DataFrame(operaciones_periodo).to_excel(writer, sheet_name='Operaciones Período', index=False)
    
    buffer.seek(0)
    return buffer.getvalue()

def main():
    """Función principal que ejecuta la aplicación Streamlit."""
    st.title("📊 Convertidor de Extractos Bancarios PDF a Excel v1.10")
    st.markdown("---")
    
    st.session_state['debug_mode'] = st.sidebar.checkbox("🔍 Modo Debug", help="Muestra información adicional para diagnóstico")
    
    with st.expander("ℹ️ Información de la aplicación"):
        st.markdown("""
        Esta aplicación convierte extractos bancarios en PDF a archivos Excel.
        - **Características**: Extrae info general, operaciones fraccionadas y del período.
        - **Formatos**: MyCard (CaixaBank), BBVA y similares.
        - **Versión 1.9**: Corregido error de sintaxis y lógica de extracción alternativa.
        """)
    
    archivo_pdf = st.file_uploader(
        "📁 Selecciona el archivo PDF del extracto bancario",
        type=['pdf'],
        help="Sube un archivo PDF de tu extracto bancario"
    )
    
    if archivo_pdf is not None:
        st.success(f"✅ Archivo cargado: {archivo_pdf.name}")
        
        if st.button("🔄 Procesar PDF", type="primary"):
            with st.spinner("Procesando archivo PDF..."):
                extractor = ExtractorExtractoBancario()
                info, op_fracc, op_per = extractor.procesar_pdf(archivo_pdf)
                
                if not info and not op_fracc and not op_per:
                    st.warning("⚠️ No se pudo extraer información del PDF. Verifique que el formato sea correcto.")
                    return

                st.success("✅ PDF procesado exitosamente")
                
                # Mostrar resultados
                if info:
                    st.subheader("📋 Información General")
                    cols = st.columns(3)
                    if 'titular' in info: cols[0].metric("Titular", info['titular'])
                    if 'periodo_inicio' in info: cols[1].metric("Período", f"{info['periodo_inicio']} - {info['periodo_fin']}")
                    if 'limite_credito' in info: cols[2].metric("Límite de Crédito", f"{info['limite_credito']} €")

                if op_fracc:
                    st.subheader("💳 Operaciones Fraccionadas")
                    st.dataframe(pd.DataFrame(op_fracc), use_container_width=True)
                
                if op_per:
                    st.subheader("🛒 Operaciones del Período")
                    st.dataframe(pd.DataFrame(op_per), use_container_width=True)

                # Botón de descarga
                try:
                    excel_data = crear_excel(info, op_fracc, op_per)
                    nombre_base = "ExtractoBancario"
                    if info.get('periodo_fin'):
                        try:
                            fecha_dt = datetime.strptime(info['periodo_fin'], '%d.%m.%Y')
                            nombre_base = f"{fecha_dt.strftime('%Y-%m-%d')}_Extracto"
                        except ValueError:
                            pass # Mantener nombre base si el formato de fecha no es el esperado
                    
                    nombre_archivo = f"{nombre_base}.xlsx"

                    st.download_button(
                        label="📊 Descargar archivo Excel",
                        data=excel_data,
                        file_name=nombre_archivo,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.error(f"❌ Error al generar el archivo Excel: {str(e)}")

if __name__ == "__main__":
    main()
