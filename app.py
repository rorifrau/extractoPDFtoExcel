import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime
import io
import base64
from typing import Dict, List, Tuple, Optional
import unicodedata

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
            # Evitar rango inválido en clase de caracteres: el guion debe estar al final o escapado
            'establecimiento': r'^[A-Z][A-Z\s.&0-9\-]*$'
        }

    # Patrón monetario robusto: signo opcional al inicio/fin, miles con punto o espacio, decimales con coma o punto
    PATRON_MONETARIO = r'(?:-)?(?:\d{1,3}(?:[\.\s]\d{3})*(?:[\.,]\d{2})|\d+[\.,]\d{2})(?:-)?'

    def normalizar_texto(self, texto: str) -> str:
        """Normaliza texto extraído del PDF para mejorar el parseo."""
        if not texto:
            return ""
        texto_norm = unicodedata.normalize('NFKC', texto)
        texto_norm = texto_norm.replace('\r\n', '\n').replace('\r', '\n')
        texto_norm = texto_norm.replace('\xa0', ' ').replace('\u00A0', ' ')
        texto_norm = texto_norm.replace('–', '-').replace('—', '-')
        # Estándar dd.mm.yyyy
        texto_norm = re.sub(r'(\d{2})[/-](\d{2})[/-](\d{4})', r'\1.\2.\3', texto_norm)
        # Forzar salto de línea antes de fechas pegadas
        texto_norm = re.sub(r'(?<!\n)(\d{2}[\./-]\d{2}[\./-]\d{4})', r'\n\1', texto_norm)
        # Normalizar PROXIMO -> PRÓXIMO
        texto_norm = re.sub(r'PROXIMO', 'PRÓXIMO', texto_norm, flags=re.IGNORECASE)
        # Compactar espacios por línea y eliminar vacías
        lineas = [re.sub(r'[ \t\f\v]+', ' ', linea).strip() for linea in texto_norm.split('\n')]
        lineas = [l for l in lineas if l]
        return '\n'.join(lineas)

    def parsear_importe(self, valor: str) -> float:
        """Convierte una cadena monetaria a float manejando miles y distintos separadores."""
        if not valor:
            return 0.0
        s = valor.strip().replace('€', '').replace(' ', '')
        # Paréntesis como negativo
        if s.startswith('(') and s.endswith(')'):
            s = '-' + s[1:-1]
        # Signo negativo al final
        if s.endswith('-') and not s.startswith('-'):
            s = '-' + s[:-1]
        if ',' in s and '.' in s:
            s = s.replace('.', '')
        s = s.replace(',', '.')
        try:
            return float(s)
        except ValueError:
            return 0.0

    def normalizar_plazo(self, valor: str) -> str:
        """Normaliza el texto del plazo para formato consistente."""
        if not valor:
            return ""
        # Asegurar espacios alrededor de 'De'
        valor = re.sub(r"(\d)\s*De\s*(\d)", r"\1 De \2", valor, flags=re.IGNORECASE)
        # Unificar separadores de fecha a dd.mm.yyyy
        valor = re.sub(r"(\d{2})[\./-](\d{2})[\./-](\d{4})", r"\1.\2.\3", valor)
        return valor.strip()

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
        
        # Buscar límite de crédito (con/sin tilde, con miles)
        patron_limite = rf'L[ÍI]MITE.*?({self.PATRON_MONETARIO})'
        match_limite = re.search(patron_limite, texto, re.IGNORECASE)
        if match_limite:
            info['limite_credito'] = str(self.parsear_importe(match_limite.group(1)))
        
        return info
    
    def extraer_operaciones_fraccionadas(self, texto: str, pdf_id: str = "default") -> List[Dict]:
        """Extrae operaciones fraccionadas del texto"""
        operaciones = []
        
        # Debug mejorado: Siempre mostrar información básica si está activado
        if st.session_state.get('debug_mode', False):
            st.write(f"🔍 **Debug para PDF: {pdf_id}**")
            st.write(f"📄 Longitud del texto extraído: {len(texto)} caracteres")
            # TEMPORAL: Mostrar texto sin condiciones
            st.write("**TEXTO EXTRAÍDO (primeros 2000 caracteres):**")
            st.text(texto[:2000])
            st.write("**TEXTO EXTRAÍDO (caracteres 2000-4000):**") 
            st.text(texto[2000:4000])
            
            if len(texto) > 0:
                st.text_area("🔍 Fragmento del texto extraído (primeros 2000 caracteres)", 
                            texto[:2000], 
                            height=200,
                            key=f"debug_texto_extraido_{pdf_id}")
            else:
                st.error("❌ Texto extraído está vacío - problema en la lectura del PDF")
                return operaciones
        
        # Método 1: Buscar operaciones en formato de líneas individuales (BBVA/CAIXA)
        lineas = texto.split('\n')
        i = 0
        while i < len(lineas):
            linea = lineas[i].strip()
            
            if re.search(r'^\d{2}\.\d{2}\.\d{4}.*(B\.?B\.?V\.?A\.?|CAJ\.LA\s*CAIXA)', linea, re.IGNORECASE):
                try:
                    partes = linea.split()
                    fecha = partes[0]
                    
                    patron_numero_completo = rf'^(?:{self.PATRON_MONETARIO})$'
                    numeros = []
                    concepto_partes = []
                    
                    for parte in partes[1:]:
                        if re.match(patron_numero_completo, parte):
                            try:
                                numeros.append(self.parsear_importe(parte))
                            except ValueError:
                                continue
                        elif parte.upper() not in ['B.B.V.A.', 'BBVA', 'CAJ.LA', 'CAIXA', 'OF.7102', 'OF.7104']:
                            concepto_partes.append(parte)
                    
                    concepto = ' '.join(concepto_partes).strip()
                    if re.search(r'B\.?B\.?V\.?A\.?', linea, re.IGNORECASE):
                        concepto = 'B.B.V.A.' if not concepto else concepto
                    elif re.search(r'CAJ\.LA\s*CAIXA', linea, re.IGNORECASE):
                        concepto = 'CAJ.LA CAIXA' if not concepto else concepto
                    
                    plazo = ""
                    importe_pendiente_despues = 0.0
                    
                    # Buscar plazo en la misma línea y en una ventana multi-línea alrededor (i-3 .. i+11)
                    patron_plazo = r'(?:Plazo\s*[:\-]?\s*(\d+\s*De\s*\d+)|PRÓXIMO\s*PLAZO\s*[:\-]?\s*(\d{2}[\./-]\d{2}[\./-]\d{4}))'
                    ventana_segmento = lineas[max(0, i-3):min(i+12, len(lineas))]
                    ventana_lineas = " \n".join([l.strip() for l in ventana_segmento])
                    plazo_win = re.search(patron_plazo, ventana_lineas, re.IGNORECASE)
                    if plazo_win:
                        plazo = plazo_win.group(1) if plazo_win.group(1) else plazo_win.group(2)
                        plazo = self.normalizar_plazo(plazo)

                    for j in range(i+1, min(i+12, len(lineas))):
                        if j >= len(lineas):
                            break
                        linea_siguiente = lineas[j].strip()
                        
                        if not plazo:
                            plazo_match = re.search(patron_plazo, linea_siguiente, re.IGNORECASE)
                            if plazo_match:
                                plazo = plazo_match.group(1) if plazo_match.group(1) else plazo_match.group(2)
                                plazo = self.normalizar_plazo(plazo)
                        
                        if "Importe pendiente después" in linea_siguiente or "Importependientedespués" in linea_siguiente:
                            pendiente_match = re.search(self.PATRON_MONETARIO, linea_siguiente)
                            if pendiente_match:
                                try:
                                    # PATRON_MONETARIO no tiene grupo de captura; usar group(0)
                                    importe_pendiente_despues = self.parsear_importe(pendiente_match.group(0))
                                except ValueError:
                                    pass
                    
                    if len(numeros) >= 1:
                        operacion = {
                            'fecha': fecha,
                            'concepto': concepto,
                            'importe_operacion': numeros[0],
                            'importe_pendiente': numeros[1] if len(numeros) > 1 else 0.0,
                            'capital_amortizado': numeros[2] if len(numeros) > 2 else 0.0,
                            'intereses': numeros[3] if len(numeros) > 3 else 0.0,
                            'cuota_mensual': numeros[4] if len(numeros) > 4 else 0.0,
                            'plazo': plazo,
                            'importe_pendiente_despues': importe_pendiente_despues,
                            'debug_ctx': ventana_lineas if st.session_state.get('debug_mode', False) else ''
                        }
                        operaciones.append(operacion)
                        
                        if st.session_state.get('debug_mode', False):
                            st.write(f"✅ Operación fraccionada (método 1): {fecha} - {concepto} - Plazo: {plazo}")
                
                except (ValueError, IndexError) as e:
                    if st.session_state.get('debug_mode', False):
                        st.write(f"❌ Error en método 1: {str(e)}")
                    continue
            i += 1
        
        # Método 2: Buscar operaciones en formato de texto continuo (CaixaBank)
        if len(operaciones) == 0:
            if st.session_state.get('debug_mode', False):
                st.write("🔄 Método 1 no encontró operaciones, probando método 2 (texto continuo)...")
            
            # Patrón mejorado para operaciones fraccionadas en texto continuo con importes robustos
            patron_texto_continuo = rf'(\d{{2}}\.\d{{2}}\.\d{{4}})\s*(CAJ\.LA\s*CAIXA|COMERCIAL\s*MAYORARTE)\s*(?:OF\.\d{{4}})?\s*(?:INNOV)?\s*({self.PATRON_MONETARIO})\s*({self.PATRON_MONETARIO})\s*({self.PATRON_MONETARIO})\s*({self.PATRON_MONETARIO})\s*({self.PATRON_MONETARIO})'
            
            matches = re.finditer(patron_texto_continuo, texto, re.IGNORECASE | re.DOTALL)
            
            matches_encontrados = 0
            for match in matches:
                matches_encontrados += 1
                try:
                    fecha = match.group(1)
                    concepto = match.group(2).replace(' ', ' ').strip()
                    importe_operacion = self.parsear_importe(match.group(3))
                    importe_pendiente = self.parsear_importe(match.group(4))
                    capital_amortizado = self.parsear_importe(match.group(5))
                    intereses = self.parsear_importe(match.group(6))
                    cuota_mensual = self.parsear_importe(match.group(7))
                    
                    # Buscar plazo en el texto cercano
                    plazo = ""
                    texto_alrededor = texto[match.start()-100:match.end()+300]
                    plazo_match = re.search(r'(?:Plazo\s*[:\-]?\s*(\d+\s*De\s*\d+)|PRÓXIMO\s*PLAZO\s*[:\-]?\s*(\d{2}[\./-]\d{2}[\./-]\d{4}))', texto_alrededor, re.IGNORECASE)
                    if plazo_match:
                        plazo = plazo_match.group(1) if plazo_match.group(1) else plazo_match.group(2)
                        plazo = self.normalizar_plazo(plazo)
                    
                    # Buscar importe pendiente después
                    importe_pendiente_despues = 0.0
                    pendiente_match = re.search(rf'Importe.*?pendiente.*?después.*?({self.PATRON_MONETARIO})', texto_alrededor, re.IGNORECASE)
                    if pendiente_match:
                        try:
                            # Si el patrón no define grupo de captura, usar group(0)
                            valor = pendiente_match.group(1) if pendiente_match.lastindex else pendiente_match.group(0)
                            importe_pendiente_despues = self.parsear_importe(valor)
                        except ValueError:
                            pass
                    
                    operacion = {
                        'fecha': fecha,
                        'concepto': concepto,
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
                        st.write(f"✅ Operación fraccionada (método 2): {fecha} - {concepto} - Plazo: {plazo}")
                        
                except (ValueError, IndexError) as e:
                    if st.session_state.get('debug_mode', False):
                        st.write(f"❌ Error en método 2: {str(e)}")
                    continue
            
            if st.session_state.get('debug_mode', False):
                st.write(f"🔍 Método 2: {matches_encontrados} coincidencias de patrón, {len(operaciones)} operaciones válidas")
        
        # Método 3: Buscar operaciones usando patrones más específicos
        if len(operaciones) == 0:
            if st.session_state.get('debug_mode', False):
                st.write("🔄 Método 2 no encontró operaciones, probando método 3 (patrones específicos)...")
            
            # Buscar línea por línea patrones de tabla
            lineas = texto.split('\n')
            for i, linea in enumerate(lineas):
                linea = linea.strip()
                
                # Buscar líneas que contengan fechas y CAJ.LA CAIXA
                if re.search(r'\d{2}\.\d{2}\.\d{4}.*CAJ\.LA\s*CAIXA', linea):
                    if st.session_state.get('debug_mode', False):
                        st.write(f"🔍 Línea encontrada: {linea[:100]}...")
                    
                    # Intentar extraer números de esta línea
                    numeros = re.findall(self.PATRON_MONETARIO, linea)
                    if len(numeros) >= 5:
                        try:
                            fecha_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', linea)
                            if fecha_match:
                                fecha = fecha_match.group(1)
                                
                                operacion = {
                                    'fecha': fecha,
                                    'concepto': 'CAJ.LA CAIXA',
                                    'importe_operacion': self.parsear_importe(numeros[0]),
                                    'importe_pendiente': self.parsear_importe(numeros[1]),
                                    'capital_amortizado': self.parsear_importe(numeros[2]),
                                    'intereses': self.parsear_importe(numeros[3]),
                                    'cuota_mensual': self.parsear_importe(numeros[4]),
                                    'plazo': '',
                                    'importe_pendiente_despues': 0.0,
                                    'debug_ctx': linea if st.session_state.get('debug_mode', False) else ''
                                }
                                operaciones.append(operacion)
                                
                                if st.session_state.get('debug_mode', False):
                                    st.write(f"✅ Operación fraccionada (método 3): {fecha}")
                                    
                        except (ValueError, IndexError) as e:
                            if st.session_state.get('debug_mode', False):
                                st.write(f"❌ Error procesando línea método 3: {str(e)}")
                            continue
        
        # Método 4: REEMPLAZADO - Extracción específica de sección IMPORTE OPERACIONES FRACCIONADAS
        # Limpiar operaciones anteriores para usar SOLO esta sección
        operaciones = []
        
        if st.session_state.get('debug_mode', False):
            st.write("🔄 Método 4: Extracción por sección específica IMPORTE OPERACIONES FRACCIONADAS → TOTAL OPERACIONES FRACCIONADAS")
            # Debug: Buscar las palabras clave por separado y mostrar contexto
            texto_upper = texto.upper()
            if 'IMPORTE' in texto_upper:
                pos = texto_upper.find('IMPORTE')
                contexto = texto[max(0, pos-50):pos+100]
                st.write("✅ Palabra 'IMPORTE' encontrada")
                st.text(f"Contexto: ...{contexto}...")
            else:
                st.write("❌ Palabra 'IMPORTE' NO encontrada")
            
            if 'FRACCIONADAS' in texto_upper:
                pos = texto_upper.find('FRACCIONADAS')
                contexto = texto[max(0, pos-50):pos+100]
                st.write("✅ Palabra 'FRACCIONADAS' encontrada")
                st.text(f"Contexto: ...{contexto}...")
            else:
                st.write("❌ Palabra 'FRACCIONADAS' NO encontrada")
                
            if 'TOTAL' in texto_upper:
                pos = texto_upper.find('TOTAL')
                contexto = texto[max(0, pos-50):pos+100]
                st.write("✅ Palabra 'TOTAL' encontrada")
                st.text(f"Contexto: ...{contexto}...")
            else:
                st.write("❌ Palabra 'TOTAL' NO encontrada")
        
        # Buscar la sección específica delimitada - Varios patrones
        patron_seccion = r'IMPORTE\s+OPERACIONES\s+FRACCIONADAS.*?TOTAL\s+OPERACIONES\s+FRACCIONADAS'
        match_seccion = re.search(patron_seccion, texto, re.DOTALL | re.IGNORECASE)
        
        if st.session_state.get('debug_mode', False):
            if match_seccion:
                st.write("✅ Patrón principal encontrado")
            else:
                st.write("❌ Patrón principal NO encontrado, probando alternativas...")
                # Probar patrones alternativos
                patrones_alt = [
                    r'IMPORTE.*?OPERACIONES.*?FRACCIONADAS.*?TOTAL.*?OPERACIONES.*?FRACCIONADAS',
                    r'OPERACIONES\s+FRACCIONADAS.*?TOTAL.*?FRACCIONADAS',
                    r'FRACCIONADAS.*?TOTAL.*?FRACCIONADAS',
                ]
                for i, patron_alt in enumerate(patrones_alt):
                    match_alt = re.search(patron_alt, texto, re.DOTALL | re.IGNORECASE)
                    if match_alt:
                        st.write(f"✅ Patrón alternativo {i+1} encontrado")
                        match_seccion = match_alt
                        break
                    else:
                        st.write(f"❌ Patrón alternativo {i+1} NO encontrado")
        
        if match_seccion:
            seccion_texto = match_seccion.group(0)
            if st.session_state.get('debug_mode', False):
                st.write(f"✅ Sección específica encontrada ({len(seccion_texto)} caracteres)")
                st.text_area("📄 Texto de la sección", seccion_texto, height=200, key=f"seccion_fraccionadas_{pdf_id}")
            
            # Procesar línea por línea en la sección
            lineas_seccion = seccion_texto.split('\n')
            i = 0
            while i < len(lineas_seccion):
                linea = lineas_seccion[i].strip()
                
                # Detectar inicio de operación por fecha en formato DD.MM.YYYY
                if re.match(r'^\d{2}\.\d{2}\.\d{4}', linea):
                    if st.session_state.get('debug_mode', False):
                        st.write(f"📅 Fecha detectada: {linea}")
                    
                    try:
                        # Reunir líneas hasta la siguiente fecha o fin de sección
                        bloque_operacion = [linea]
                        j = i + 1
                        while j < len(lineas_seccion):
                            siguiente_linea = lineas_seccion[j].strip()
                            # Parar si encontramos otra fecha o línea de total
                            if (re.match(r'^\d{2}\.\d{2}\.\d{4}', siguiente_linea) or 
                                'TOTAL OPERACIONES' in siguiente_linea.upper()):
                                break
                            if siguiente_linea:  # Solo añadir líneas no vacías
                                bloque_operacion.append(siguiente_linea)
                            j += 1
                        
                        # Procesar el bloque completo de la operación
                        texto_operacion = ' '.join(bloque_operacion)
                        if st.session_state.get('debug_mode', False):
                            st.write(f"🔍 Bloque operación: {texto_operacion}")
                        
                        # Extraer fecha
                        fecha_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', texto_operacion)
                        fecha = fecha_match.group(1) if fecha_match else ""
                        
                        # Extraer concepto (entre fecha y primer número)
                        concepto_match = re.search(r'\d{2}\.\d{2}\.\d{4}\s+(.+?)(?=\d+[,\.]\d{2})', texto_operacion)
                        concepto = concepto_match.group(1).strip() if concepto_match else ""
                        
                        # Limpiar concepto
                        concepto = re.sub(r'\s+', ' ', concepto)  # Normalizar espacios
                        
                        # Detectar conceptos válidos de operaciones fraccionadas
                        if 'CAJ.LA CAIXA' in concepto.upper() or 'CAIXA' in concepto.upper():
                            concepto = 'CAJ.LA CAIXA'
                        elif 'COMERCIAL MAYORARTE' in concepto.upper() or 'MAYORARTE' in concepto.upper():
                            concepto = 'COMERCIAL MAYORARTE'
                        elif 'B.B.V.A' in concepto.upper() or 'BBVA' in concepto.upper():
                            concepto = 'B.B.V.A.'
                        elif concepto.upper().startswith('OF.') or len(concepto) < 4:
                            # Probablemente es una línea de referencia, no una operación
                            concepto = ""
                        
                        # Extraer números
                        numeros = re.findall(self.PATRON_MONETARIO, texto_operacion)
                        numeros_float = [self.parsear_importe(n) for n in numeros if n]
                        
                        # Buscar plazo
                        plazo = ""
                        plazo_match = re.search(r'(?:Plazo\s*[:\-]?\s*(\d+\s*De\s*\d+)|PRÓXIMO\s*PLAZO\s*[:\-]?\s*(\d{2}[\./-]\d{2}[\./-]\d{4}))', texto_operacion, re.IGNORECASE)
                        if plazo_match:
                            plazo = plazo_match.group(1) if plazo_match.group(1) else plazo_match.group(2)
                            plazo = self.normalizar_plazo(plazo)
                        
                        # Validar que sea una operación real fraccionada
                        es_operacion_valida = (
                            len(numeros_float) >= 2 and 
                            fecha and 
                            concepto and
                            # Debe tener concepto válido (no solo fecha)
                            len(concepto) > 3 and
                            # No debe ser línea de "Importe pendiente después"
                            "importe pendiente" not in concepto.lower() and
                            "liquidacion" not in concepto.lower() and
                            # Debe tener importe operación significativo (mayor a 5€)
                            numeros_float[0] >= 5.0 and
                            # Si tiene varios números, el segundo debe ser significativo o cero
                            (len(numeros_float) < 2 or numeros_float[1] >= 0)
                        )
                        
                        if es_operacion_valida:
                            operacion = {
                                'fecha': fecha,
                                'concepto': concepto,
                                'importe_operacion': numeros_float[0],
                                'importe_pendiente': numeros_float[1] if len(numeros_float) > 1 else 0.0,
                                'capital_amortizado': numeros_float[2] if len(numeros_float) > 2 else 0.0,
                                'intereses': numeros_float[3] if len(numeros_float) > 3 else 0.0,
                                'cuota_mensual': numeros_float[4] if len(numeros_float) > 4 else 0.0,
                                'plazo': plazo,
                                'importe_pendiente_despues': 0.0,
                                'debug_ctx': texto_operacion if st.session_state.get('debug_mode', False) else ''
                            }
                            operaciones.append(operacion)
                            
                            if st.session_state.get('debug_mode', False):
                                st.write(f"✅ Operación VÁLIDA extraída: {fecha} - {concepto} - {numeros_float[0]:.2f}€ - Plazo: {plazo}")
                        elif st.session_state.get('debug_mode', False):
                            st.write(f"❌ Operación RECHAZADA: {fecha} - {concepto} - {numeros_float[0] if numeros_float else 'N/A'}€ (no cumple criterios de validación)")
                        
                        i = j  # Saltar al siguiente bloque
                    
                    except Exception as e:
                        if st.session_state.get('debug_mode', False):
                            st.write(f"❌ Error procesando operación: {e}")
                        i += 1
                else:
                    i += 1
            
            if st.session_state.get('debug_mode', False):
                st.write(f"🎯 Método 4 completado: {len(operaciones)} operaciones extraídas de la sección específica")
        else:
            if st.session_state.get('debug_mode', False):
                st.error("❌ No se encontró la sección 'IMPORTE OPERACIONES FRACCIONADAS' → 'TOTAL OPERACIONES FRACCIONADAS'")
        
        # Debug detallado ANTES de deduplicar
        if st.session_state.get('debug_mode', False):
            st.write(f"🔢 Total operaciones fraccionadas ANTES de deduplicar: {len(operaciones)}")
            if operaciones:
                st.write("📋 Todas las operaciones encontradas:")
                for i, op in enumerate(operaciones):
                    st.write(f"**Operación #{i+1}:**")
                    vista = {k: v for k, v in op.items() if k != 'debug_ctx'}
                    st.json(vista)
                    ctx = op.get('debug_ctx', '')
                    if ctx:
                        with st.expander(f"🔎 Contexto cercano #{i+1}"):
                            st.text(ctx)
                    else:
                        st.write("⚠️ Sin contexto de debug capturado para esta operación")

        # Deduplicar operaciones fraccionadas con clave más completa
        unicas = []
        vistos = set()
        claves_analizadas = []
        
        for op in operaciones:
            # Clave más robusta incluyendo capital amortizado e intereses
            clave = (
                op.get('fecha'), 
                op.get('concepto','').strip().upper(), 
                round(op.get('importe_operacion',0.0), 2), 
                round(op.get('importe_pendiente',0.0), 2),
                round(op.get('capital_amortizado',0.0), 2),
                round(op.get('intereses',0.0), 2)
            )
            claves_analizadas.append(clave)
            
            if clave not in vistos:
                vistos.add(clave)
                unicas.append(op)

        if st.session_state.get('debug_mode', False):
            st.write(f"🔢 Total operaciones fraccionadas DESPUÉS de deduplicar: {len(unicas)}")
            
            # Análisis detallado de duplicados
            if len(operaciones) != len(unicas):
                st.warning(f"⚠️ Se eliminaron {len(operaciones) - len(unicas)} duplicados")
            
            st.write("🔍 Análisis detallado de claves:")
            for i, clave in enumerate(claves_analizadas):
                estado = "✅ ÚNICO" if clave in [c for j, c in enumerate(claves_analizadas) if j <= i and claves_analizadas.count(c) == 1 or (claves_analizadas.count(c) > 1 and j == claves_analizadas.index(c))] else "❌ DUPLICADO"
                st.text(f"Op #{i+1}: {estado} | {clave}")
            
            # Análisis específico si hay más de 3 operaciones
            if len(unicas) > 3:
                st.error(f"🚨 PROBLEMA: Se encontraron {len(unicas)} operaciones cuando deberían ser 3")
                st.write("📊 Análisis por campos:")
                fechas = [op.get('fecha') for op in unicas]
                conceptos = [op.get('concepto','').strip().upper() for op in unicas] 
                importes_op = [op.get('importe_operacion',0) for op in unicas]
                
                st.write(f"📅 Fechas: {fechas} (únicas: {len(set(fechas))})")
                st.write(f"🏷️ Conceptos: {conceptos} (únicos: {len(set(conceptos))})")
                st.write(f"💰 Importes operación: {importes_op} (únicos: {len(set(importes_op))})")
            
            if unicas:
                st.write("📋 Operaciones finales (deduplicadas):")
                for i, op in enumerate(unicas):
                    vista = {k: v for k, v in op.items() if k != 'debug_ctx'}
                    st.json(vista)
        
        return unicas
    
    def extraer_operaciones_periodo(self, texto: str) -> List[Dict]:
        """Extrae operaciones del período del texto"""
        operaciones = []
        
        lineas = texto.split('\n')
        
        for linea in lineas:
            linea = linea.strip()
            
            # Soporte de formato variable: fecha + establecimiento + localidad + importe
            patron_operacion = rf'^(\d{{2}}\.\d{{2}}\.\d{{4}})\s+([A-ZÁÉÍÓÚÜÑ\-/&\.\,\'\(\)0-9 ]+?)\s+([A-ZÁÉÍÓÚÜÑ\-/&\.\' ]+?)\s+({self.PATRON_MONETARIO})(?:\s|$)'
            
            match = re.match(patron_operacion, linea, re.IGNORECASE)
            if match:
                fecha = match.group(1)
                establecimiento = match.group(2).strip()
                localidad = match.group(3).strip()
                importe_str = match.group(4)
                
                try:
                    importe = self.parsear_importe(importe_str)
                    
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
                        if len(partes) >= 4:
                            try:
                                fecha = partes[0]
                                patron_numerico = rf'^(?:{self.PATRON_MONETARIO})$'
                                importe_candidatos = [p for p in partes if re.match(patron_numerico, p)]
                                
                                if importe_candidatos:
                                    importe = self.parsear_importe(importe_candidatos[-1])
                                    
                                    partes_sin_fecha_importe = partes[1:-1] if importe_candidatos else partes[1:]
                                    
                                    if len(partes_sin_fecha_importe) >= 2:
                                        # Heurística: última(s) palabra(s) en mayúsculas cortas pueden ser localidad
                                        idx_corte = len(partes_sin_fecha_importe) - 1
                                        establecimiento_tokens = partes_sin_fecha_importe[:idx_corte]
                                        localidad_tokens = partes_sin_fecha_importe[idx_corte:]
                                        establecimiento = ' '.join(establecimiento_tokens)
                                        localidad = ' '.join(localidad_tokens)
                                        
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
            st.write(f"🔢 Total operaciones del período encontradas: {len(operaciones)}")
        
        return operaciones
    
    def procesar_pdf(self, archivo_pdf) -> Tuple[Dict, List[Dict], List[Dict]]:
        """Procesa el PDF completo y extrae toda la información"""
        texto = self.extraer_texto_pdf(archivo_pdf)
        
        if not texto:
            return {}, [], []
        
        # Crear un ID único para este PDF basado en su nombre
        pdf_id = archivo_pdf.name.replace('.pdf', '').replace('.PDF', '').replace(' ', '_').replace('-', '_')
        
        # Normalización previa
        texto = self.normalizar_texto(texto)
        
        info_general = self.extraer_informacion_general(texto)
        operaciones_fraccionadas = self.extraer_operaciones_fraccionadas(texto, pdf_id)
        operaciones_periodo = self.extraer_operaciones_periodo(texto)
        
        return info_general, operaciones_fraccionadas, operaciones_periodo

def crear_excel(info_general: Dict, operaciones_fraccionadas: List[Dict], operaciones_periodo: List[Dict]) -> bytes:
    """Crea un archivo Excel con los datos extraídos"""
    
    buffer = io.BytesIO()
    
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # Siempre crear dos hojas con columnas estándar
        cols_frac = ['fecha','concepto','importe_operacion','importe_pendiente','capital_amortizado','intereses','cuota_mensual','plazo','importe_pendiente_despues']
        cols_periodo = ['fecha','establecimiento','localidad','importe']

        df_fraccionadas = pd.DataFrame(operaciones_fraccionadas, columns=cols_frac)
        df_fraccionadas.to_excel(writer, sheet_name='Operaciones Fraccionadas', index=False)
        
        df_periodo = pd.DataFrame(operaciones_periodo, columns=cols_periodo)
        df_periodo.to_excel(writer, sheet_name='Operaciones Período', index=False)
    
    buffer.seek(0)
    return buffer.getvalue()

def reiniciar_aplicacion():
    """Reinicia completamente la aplicación limpiando todo el estado"""
    # Limpiar TODO el estado de session
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    # Forzar rerun completo
    st.rerun()

def main():
    st.title("📊 Convertidor de Extractos Bancarios PDF a Excel v2.6.5.4 ")
    st.markdown("---")
    
    # Inicializar session_state para resultados
    if 'resultados_procesamiento' not in st.session_state:
        st.session_state.resultados_procesamiento = []
    if 'archivos_procesados' not in st.session_state:
        st.session_state.archivos_procesados = []
    if 'archivos_descargados' not in st.session_state:
        st.session_state.archivos_descargados = set()
    if 'limpiar_archivos' not in st.session_state:
        st.session_state.limpiar_archivos = False
    
    debug_mode = st.sidebar.checkbox("🔍 Modo Debug", help="Muestra información adicional para diagnóstico")
    if 'debug_mode' not in st.session_state:
        st.session_state['debug_mode'] = False
    st.session_state['debug_mode'] = debug_mode
    
    with st.expander("ℹ️ Información de la aplicación"):
        st.markdown("""
        ### 📋 **Extracto PDF to Excel Converter**
        
        **🎯 Funcionalidades principales:**
        - 📄 **Procesamiento de PDFs bancarios** - Extrae automáticamente datos de extractos de tarjetas de crédito
        - 📊 **Exportación a Excel** - Genera archivos .xlsx con dos hojas organizadas:
          - *Operaciones Fraccionadas* - Compras a plazos y financiaciones
          - *Operaciones del Período* - Transacciones regulares del mes
        - 🔍 **Modo Debug avanzado** - Información detallada para diagnóstico y optimización
        - 📱 **Interfaz intuitiva** - Carga múltiples archivos PDF de forma simultánea
        
        **💡 Versión actual:** v2.6.5.1 con mejoras en extracción de plazos y deduplicación
        """)
    
    # Manejar limpieza de archivos
    if st.session_state.limpiar_archivos:
        st.session_state.resultados_procesamiento = []
        st.session_state.archivos_procesados = []
        st.session_state.archivos_descargados = set()
        st.session_state.limpiar_archivos = False
        st.rerun()
    
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
        # Los archivos han cambiado, limpiar resultados anteriores
        st.session_state.resultados_procesamiento = []
        st.session_state.archivos_procesados = archivos_actuales
    
    if archivos_pdf is not None and len(archivos_pdf) > 0:
        # Mostrar archivos seleccionados
        col1, col2 = st.columns([3, 1])
        with col1:
            st.success(f"✅ {len(archivos_pdf)} archivo(s) cargado(s):")
            for i, pdf in enumerate(archivos_pdf, 1):
                st.write(f"   {i}. {pdf.name}")
        
        with col2:
            if st.button("🗑️ Limpiar todo", type="secondary", help="Eliminar todos los archivos y resultados completamente"):
                reiniciar_aplicacion()
        
        # Botón para procesar (solo si no hay resultados o han cambiado los archivos)
        if len(st.session_state.resultados_procesamiento) == 0:
            if st.button("🔄 Procesar todos los PDFs", type="primary"):
                resultados = []
                
                # Crear barra de progreso
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Procesar cada PDF
                for i, pdf in enumerate(archivos_pdf):
                    # Actualizar progreso
                    progress = (i + 1) / len(archivos_pdf)
                    progress_bar.progress(progress)
                    status_text.text(f"Procesando {pdf.name} ({i+1}/{len(archivos_pdf)})...")
                    
                    try:
                        with st.spinner(f"Procesando {pdf.name}..."):
                            extractor = ExtractorExtractoBancario()
                            info_general, operaciones_fraccionadas, operaciones_periodo = extractor.procesar_pdf(pdf)
                            
                            # Generar Excel para este PDF
                            excel_data = crear_excel(info_general, operaciones_fraccionadas, operaciones_periodo)
                            
                            # Generar nombre de archivo
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
                                        # Usar nombre base del PDF si no se encuentra fecha
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
                
                # Guardar resultados en session_state
                st.session_state.resultados_procesamiento = resultados
                
                # Limpiar barra de progreso
                progress_bar.empty()
                status_text.empty()
                
                # Forzar rerun para mostrar resultados
                st.rerun()
        
        # Mostrar resultados si existen
        if len(st.session_state.resultados_procesamiento) > 0:
            resultados = st.session_state.resultados_procesamiento
            
            # Botón para procesar de nuevo
            if st.button("🔄 Procesar nuevamente", type="secondary"):
                st.session_state.resultados_procesamiento = []
                st.session_state.archivos_descargados = set()
                st.rerun()
            
            st.success(f"✅ Procesamiento completado de {len(archivos_pdf)} archivo(s)")
            
            # Estadísticas generales
            exitosos = len([r for r in resultados if r['estado'] == 'success'])
            errores = len([r for r in resultados if r['estado'] == 'error'])
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("📊 Procesados exitosamente", exitosos)
            with col2:
                st.metric("❌ Con errores", errores)
            
            # Mostrar resultados individuales
            st.subheader("📋 Resultados por archivo")
            
            for resultado in resultados:
                if resultado['estado'] == 'success':
                    with st.container():
                        st.markdown(f"### ✅ {resultado['nombre_pdf']}")
                        
                        # Métricas del archivo
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
                        
                        # Botón de descarga con estado
                        if resultado['excel_data']:
                            archivo_descargado = resultado['nombre_pdf'] in st.session_state.archivos_descargados
                            
                            if archivo_descargado:
                                # Mostrar como descargado
                                st.success("✅ Descargado")
                                if st.button(f"📥 Volver a descargar - {resultado['nombre_excel']}", 
                                           key=f"redownload_{resultado['nombre_pdf']}_{hash(resultado['nombre_pdf'])}"):
                                    pass  # El botón download_button se encargará
                            
                            # Botón de descarga (siempre presente)
                            if st.download_button(
                                label=f"📥 {'Descargar de nuevo' if archivo_descargado else 'Descargar Excel'} - {resultado['nombre_excel']}",
                                data=resultado['excel_data'],
                                file_name=resultado['nombre_excel'],
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"download_{resultado['nombre_pdf']}_{hash(resultado['nombre_pdf'])}"
                            ):
                                # Marcar como descargado
                                st.session_state.archivos_descargados.add(resultado['nombre_pdf'])
                        
                        # Debug info si está activado
                        if debug_mode:
                            with st.expander(f"🔍 Debug info para {resultado['nombre_pdf']}"):
                                st.write("### 📊 Resumen")
                                st.json({
                                    'operaciones_fraccionadas': len(resultado['operaciones_fraccionadas']),
                                    'operaciones_periodo': len(resultado['operaciones_periodo']),
                                    'info_general': resultado['info_general']
                                })
                                
                                st.write("### 🔍 Operaciones Fraccionadas Detalladas")
                                if resultado['operaciones_fraccionadas']:
                                    for i, op in enumerate(resultado['operaciones_fraccionadas']):
                                        with st.expander(f"Operación #{i+1}: {op.get('fecha', 'N/A')} - {op.get('concepto', 'N/A')}"):
                                            st.json(op)
                                else:
                                    st.warning("No se encontraron operaciones fraccionadas")
                                
                                st.write("### 📋 Operaciones del Período (primeras 5)")
                                if resultado['operaciones_periodo']:
                                    for i, op in enumerate(resultado['operaciones_periodo'][:5]):
                                        st.json(op)
                                    if len(resultado['operaciones_periodo']) > 5:
                                        st.info(f"... y {len(resultado['operaciones_periodo']) - 5} más")
                                else:
                                    st.warning("No se encontraron operaciones del período")
                        
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
        Convertidor de Extractos Bancarios v2.4 ORIGINAL | Código que funcionaba antes | Sin hoja Resumen | ROF
        </div>
        """, 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
