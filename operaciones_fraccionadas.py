"""
Módulo especializado para extraer operaciones fraccionadas de extractos bancarios.
Enfocado en resolver problemas específicos de formato y patrones.

Versión 2.6 - Modular
"""

import re
import streamlit as st
from typing import List, Dict, Optional, Tuple

class ExtractorOperacionesFraccionadas:
    """Clase especializada en extraer operaciones fraccionadas con múltiples estrategias"""
    
    def __init__(self):
        self.patrones_caixabank = {
            # Patrón tabla estándar: FECHA CAJ.LA CAIXA OF.XXXX NUMS...
            'tabla_estandar': r'(\d{2}\.\d{2}\.\d{4})\s+CAJ\.LA\s*CAIXA\s+(?:OF\.\d{4})?\s*(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})',
            
            # Patrón más flexible para casos con espaciado irregular
            'tabla_flexible': r'(\d{2}\.\d{2}\.\d{4})\s+CAJ\.LA\s*CAIXA.*?(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})',
            
            # Patrón para una sola línea con múltiples números
            'linea_simple': r'(\d{2}\.\d{2}\.\d{4}).*?CAJ\.LA\s*CAIXA.*?(\d+[,\.]\d{2})',
            
            # Patrón para buscar en múltiples líneas
            'multilinea': r'(\d{2}\.\d{2}\.\d{4})\s+CAJ\.LA\s*CAIXA\s+OF\.\d{4}'
        }
        
        self.patrones_bbva = {
            'estandar': r'(\d{2}\.\d{2}\.\d{4}).*?B\.B\.V\.A\..*?(\d+[,\.]\d{2})'
        }
    
    def extraer_operaciones_fraccionadas(self, texto: str, pdf_id: str = "default") -> List[Dict]:
        """
        Método principal que coordina todos los enfoques de extracción
        """
        operaciones = []
        
        if st.session_state.get('debug_mode', False):
            st.write(f"🔧 **MÓDULO ESPECIALIZADO FRACCIONADAS** - PDF: {pdf_id}")
            st.write(f"📊 Texto total: {len(texto)} caracteres")
        
        # ESTRATEGIA 1: Buscar sección específica primero
        seccion_texto = self._buscar_seccion_fraccionadas(texto, pdf_id)
        
        if seccion_texto:
            # MÉTODO 1: Formato tabla CaixaBank estándar
            operaciones.extend(self._extraer_tabla_caixabank_estandar(seccion_texto, pdf_id))
            
            # MÉTODO 2: Formato tabla flexible si no encontramos suficientes
            if len(operaciones) < 5:
                operaciones.extend(self._extraer_tabla_caixabank_flexible(seccion_texto, pdf_id))
            
            # MÉTODO 3: Línea por línea dentro de la sección
            if len(operaciones) < 5:
                operaciones.extend(self._extraer_linea_por_linea_seccion(seccion_texto, pdf_id))
        
        # ESTRATEGIA 2: Buscar en todo el texto si no encontramos en la sección
        if len(operaciones) < 5:
            operaciones.extend(self._extraer_texto_completo(texto, pdf_id))
        
        # ESTRATEGIA 3: Métodos de respaldo
        if len(operaciones) == 0:
            operaciones.extend(self._extraer_metodos_respaldo(texto, pdf_id))
        
        # Eliminar duplicados
        operaciones = self._eliminar_duplicados(operaciones)
        
        if st.session_state.get('debug_mode', False):
            self._mostrar_resumen_debug(operaciones, pdf_id)
        
        return operaciones
    
    def _buscar_seccion_fraccionadas(self, texto: str, pdf_id: str) -> Optional[str]:
        """Busca la sección específica de operaciones fraccionadas"""
        
        # Patrón para encontrar la sección
        patrones_seccion = [
            r'IMPORTE OPERACIONES FRACCIONADAS(.*?)(?=OPERACIONES DE LA TARJETA|$)',
            r'OPERACIONES FRACCIONADAS(.*?)(?=OPERACIONES DE LA TARJETA|$)',
            r'FRACCIONADAS(.*?)(?=OPERACIONES DE LA TARJETA|TOTAL OPERACIONES|$)'
        ]
        
        for patron in patrones_seccion:
            match = re.search(patron, texto, re.DOTALL | re.IGNORECASE)
            if match:
                seccion = match.group(1)
                if st.session_state.get('debug_mode', False):
                    st.write(f"✅ Sección fraccionadas encontrada: {len(seccion)} caracteres")
                    st.text_area(f"Sección completa - {pdf_id}", seccion, height=300, key=f"seccion_{pdf_id}")
                return seccion
        
        if st.session_state.get('debug_mode', False):
            st.write("⚠️ No se encontró sección específica de fraccionadas")
        
        return None
    
    def _extraer_tabla_caixabank_estandar(self, texto: str, pdf_id: str) -> List[Dict]:
        """Extrae operaciones usando el patrón de tabla estándar"""
        operaciones = []
        
        if st.session_state.get('debug_mode', False):
            st.write(f"🔍 **MÉTODO 1: Tabla CaixaBank Estándar**")
        
        patron = self.patrones_caixabank['tabla_estandar']
        matches = re.finditer(patron, texto, re.IGNORECASE)
        
        for i, match in enumerate(matches, 1):
            try:
                fecha = match.group(1)
                importe_operacion = float(match.group(2).replace(',', '.'))
                importe_pendiente = float(match.group(3).replace(',', '.'))
                capital_amortizado = float(match.group(4).replace(',', '.'))
                intereses = float(match.group(5).replace(',', '.'))
                cuota_mensual = float(match.group(6).replace(',', '.'))
                
                # Buscar información adicional en el contexto
                plazo, importe_pendiente_despues = self._buscar_info_adicional(texto, match)
                
                operacion = {
                    'fecha': fecha,
                    'concepto': 'CAJ.LA CAIXA',
                    'importe_operacion': importe_operacion,
                    'importe_pendiente': importe_pendiente,
                    'capital_amortizado': capital_amortizado,
                    'intereses': intereses,
                    'cuota_mensual': cuota_mensual,
                    'plazo': plazo,
                    'importe_pendiente_despues': importe_pendiente_despues,
                    'metodo_extraccion': 'tabla_estandar'
                }
                
                operaciones.append(operacion)
                
                if st.session_state.get('debug_mode', False):
                    st.write(f"   ✅ Op {i}: {fecha} - {importe_operacion}€ - Plazo: {plazo}")
            
            except Exception as e:
                if st.session_state.get('debug_mode', False):
                    st.write(f"   ❌ Error en match {i}: {str(e)}")
                continue
        
        if st.session_state.get('debug_mode', False):
            st.write(f"📊 Método 1 encontró: {len(operaciones)} operaciones")
        
        return operaciones
    
    def _extraer_tabla_caixabank_flexible(self, texto: str, pdf_id: str) -> List[Dict]:
        """Extrae operaciones usando un patrón más flexible"""
        operaciones = []
        
        if st.session_state.get('debug_mode', False):
            st.write(f"🔄 **MÉTODO 2: Tabla CaixaBank Flexible**")
        
        # Buscar líneas que contengan fecha + CAJ.LA CAIXA + múltiples números
        lineas = texto.split('\n')
        
        for i, linea in enumerate(lineas):
            linea = linea.strip()
            
            # Verificar si la línea contiene los elementos básicos
            if re.search(r'\d{2}\.\d{2}\.\d{4}.*CAJ\.LA\s*CAIXA', linea, re.IGNORECASE):
                if st.session_state.get('debug_mode', False):
                    st.write(f"   🔍 Línea candidata {i+1}: {linea}")
                
                try:
                    # Extraer fecha
                    fecha_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', linea)
                    if not fecha_match:
                        continue
                    
                    fecha = fecha_match.group(1)
                    
                    # Extraer todos los números decimales de la línea
                    numeros = re.findall(r'\d+[,\.]\d{2}', linea)
                    
                    if st.session_state.get('debug_mode', False):
                        st.write(f"      📅 Fecha: {fecha}")
                        st.write(f"      💰 Números: {numeros}")
                    
                    if len(numeros) >= 1:
                        numeros_float = [float(n.replace(',', '.')) for n in numeros]
                        
                        # Buscar información adicional en líneas siguientes
                        plazo, importe_pendiente_despues = self._buscar_info_lineas_siguientes(lineas, i)
                        
                        operacion = {
                            'fecha': fecha,
                            'concepto': 'CAJ.LA CAIXA',
                            'importe_operacion': numeros_float[0],
                            'importe_pendiente': numeros_float[1] if len(numeros_float) > 1 else numeros_float[0],
                            'capital_amortizado': numeros_float[2] if len(numeros_float) > 2 else 0.0,
                            'intereses': numeros_float[3] if len(numeros_float) > 3 else 0.0,
                            'cuota_mensual': numeros_float[4] if len(numeros_float) > 4 else 0.0,
                            'plazo': plazo,
                            'importe_pendiente_despues': importe_pendiente_despues,
                            'metodo_extraccion': 'tabla_flexible'
                        }
                        
                        operaciones.append(operacion)
                        
                        if st.session_state.get('debug_mode', False):
                            st.write(f"   ✅ Flexible: {fecha} - {numeros_float[0]}€ - Plazo: {plazo}")
                
                except Exception as e:
                    if st.session_state.get('debug_mode', False):
                        st.write(f"   ❌ Error línea {i+1}: {str(e)}")
                    continue
        
        if st.session_state.get('debug_mode', False):
            st.write(f"📊 Método 2 encontró: {len(operaciones)} operaciones adicionales")
        
        return operaciones
    
    def _extraer_linea_por_linea_seccion(self, texto: str, pdf_id: str) -> List[Dict]:
        """Análisis línea por línea dentro de la sección"""
        operaciones = []
        
        if st.session_state.get('debug_mode', False):
            st.write(f"🔄 **MÉTODO 3: Línea por Línea en Sección**")
        
        lineas = texto.split('\n')
        
        for i, linea in enumerate(lineas):
            linea_original = linea
            linea = linea.strip()
            
            # Buscar cualquier línea con fecha y referencia a fraccionadas
            if re.search(r'\d{2}\.\d{2}\.\d{4}', linea) and any(palabra in linea.upper() for palabra in ['CAJ.LA', 'CAIXA', 'FRACCION']):
                if st.session_state.get('debug_mode', False):
                    st.write(f"   🔍 Análisis línea {i+1}: {linea}")
                
                try:
                    # Buscar fecha
                    fecha_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', linea)
                    if fecha_match:
                        fecha = fecha_match.group(1)
                        
                        # Buscar números en esta línea y las siguientes
                        numeros_contexto = []
                        
                        # Números de la línea actual
                        numeros_linea = re.findall(r'\d+[,\.]\d{2}', linea)
                        numeros_contexto.extend(numeros_linea)
                        
                        # Números de las 3 líneas siguientes
                        for j in range(i+1, min(i+4, len(lineas))):
                            if j < len(lineas):
                                numeros_siguiente = re.findall(r'\d+[,\.]\d{2}', lineas[j])
                                numeros_contexto.extend(numeros_siguiente)
                        
                        if st.session_state.get('debug_mode', False):
                            st.write(f"      📅 Fecha: {fecha}")
                            st.write(f"      💰 Números contexto: {numeros_contexto}")
                        
                        if len(numeros_contexto) >= 1:
                            numeros_float = [float(n.replace(',', '.')) for n in numeros_contexto]
                            
                            operacion = {
                                'fecha': fecha,
                                'concepto': 'CAJ.LA CAIXA',
                                'importe_operacion': numeros_float[0],
                                'importe_pendiente': numeros_float[1] if len(numeros_float) > 1 else numeros_float[0],
                                'capital_amortizado': numeros_float[2] if len(numeros_float) > 2 else 0.0,
                                'intereses': numeros_float[3] if len(numeros_float) > 3 else 0.0,
                                'cuota_mensual': numeros_float[4] if len(numeros_float) > 4 else 0.0,
                                'plazo': '',
                                'importe_pendiente_despues': 0.0,
                                'metodo_extraccion': 'linea_seccion'
                            }
                            
                            operaciones.append(operacion)
                            
                            if st.session_state.get('debug_mode', False):
                                st.write(f"   ✅ Línea sección: {fecha} - {numeros_float[0]}€")
                
                except Exception as e:
                    if st.session_state.get('debug_mode', False):
                        st.write(f"   ❌ Error análisis línea {i+1}: {str(e)}")
                    continue
        
        if st.session_state.get('debug_mode', False):
            st.write(f"📊 Método 3 encontró: {len(operaciones)} operaciones adicionales")
        
        return operaciones
    
    def _extraer_texto_completo(self, texto: str, pdf_id: str) -> List[Dict]:
        """Buscar en todo el texto cuando los métodos de sección fallan"""
        operaciones = []
        
        if st.session_state.get('debug_mode', False):
            st.write(f"🔄 **MÉTODO 4: Búsqueda en Texto Completo**")
        
        # Patrón muy flexible para buscar cualquier ocurrencia
        patron_global = r'(\d{2}\.\d{2}\.\d{4}).*?CAJ\.LA\s*CAIXA.*?(\d+[,\.]\d{2})'
        matches = re.finditer(patron_global, texto, re.IGNORECASE | re.DOTALL)
        
        for i, match in enumerate(matches, 1):
            try:
                fecha = match.group(1)
                importe_basico = float(match.group(2).replace(',', '.'))
                
                # Buscar más números en el contexto del match
                inicio = max(0, match.start() - 100)
                fin = min(len(texto), match.end() + 200)
                contexto = texto[inicio:fin]
                
                numeros_contexto = re.findall(r'\d+[,\.]\d{2}', contexto)
                numeros_float = [float(n.replace(',', '.')) for n in numeros_contexto]
                
                if st.session_state.get('debug_mode', False):
                    st.write(f"   🔍 Match global {i}: {fecha} - Contexto: {numeros_contexto}")
                
                operacion = {
                    'fecha': fecha,
                    'concepto': 'CAJ.LA CAIXA',
                    'importe_operacion': importe_basico,
                    'importe_pendiente': numeros_float[1] if len(numeros_float) > 1 else importe_basico,
                    'capital_amortizado': numeros_float[2] if len(numeros_float) > 2 else 0.0,
                    'intereses': numeros_float[3] if len(numeros_float) > 3 else 0.0,
                    'cuota_mensual': numeros_float[4] if len(numeros_float) > 4 else 0.0,
                    'plazo': '',
                    'importe_pendiente_despues': 0.0,
                    'metodo_extraccion': 'texto_completo'
                }
                
                operaciones.append(operacion)
                
                if st.session_state.get('debug_mode', False):
                    st.write(f"   ✅ Global: {fecha} - {importe_basico}€")
            
            except Exception as e:
                if st.session_state.get('debug_mode', False):
                    st.write(f"   ❌ Error match global {i}: {str(e)}")
                continue
        
        if st.session_state.get('debug_mode', False):
            st.write(f"📊 Método 4 encontró: {len(operaciones)} operaciones adicionales")
        
        return operaciones
    
    def _extraer_metodos_respaldo(self, texto: str, pdf_id: str) -> List[Dict]:
        """Métodos de último recurso"""
        operaciones = []
        
        if st.session_state.get('debug_mode', False):
            st.write(f"🆘 **MÉTODO 5: Respaldo de Emergencia**")
            
            # Mostrar estadísticas del texto para diagnosticar
            menciones_caixa = re.findall(r'.*CAJ\.LA CAIXA.*', texto, re.IGNORECASE)
            fechas = re.findall(r'\d{2}\.\d{2}\.\d{4}', texto)
            numeros = re.findall(r'\d+[,\.]\d{2}', texto)
            
            st.write(f"   📊 Estadísticas de respaldo:")
            st.write(f"      - Menciones CAJ.LA CAIXA: {len(menciones_caixa)}")
            st.write(f"      - Fechas encontradas: {len(fechas)}")
            st.write(f"      - Números decimales: {len(numeros)}")
            
            if len(menciones_caixa) > 0:
                st.write(f"   📋 Primeras menciones:")
                for i, mencion in enumerate(menciones_caixa[:10]):
                    st.write(f"      {i+1}. {mencion}")
        
        # Buscar al menos las fechas con CAJ.LA CAIXA
        patron_minimo = r'(\d{2}\.\d{2}\.\d{4}).*?CAJ\.LA\s*CAIXA'
        matches = re.finditer(patron_minimo, texto, re.IGNORECASE)
        
        for match in matches:
            fecha = match.group(1)
            
            # Buscar el primer número después de CAJ.LA CAIXA en esta línea
            linea_match = texto[match.start():match.start()+200]  # 200 caracteres después
            numero_match = re.search(r'(\d+[,\.]\d{2})', linea_match)
            
            if numero_match:
                try:
                    importe = float(numero_match.group(1).replace(',', '.'))
                    
                    operacion = {
                        'fecha': fecha,
                        'concepto': 'CAJ.LA CAIXA',
                        'importe_operacion': importe,
                        'importe_pendiente': importe,
                        'capital_amortizado': 0.0,
                        'intereses': 0.0,
                        'cuota_mensual': 0.0,
                        'plazo': '',
                        'importe_pendiente_despues': 0.0,
                        'metodo_extraccion': 'respaldo_minimo'
                    }
                    
                    operaciones.append(operacion)
                    
                    if st.session_state.get('debug_mode', False):
                        st.write(f"   🆘 Respaldo: {fecha} - {importe}€")
                
                except Exception as e:
                    if st.session_state.get('debug_mode', False):
                        st.write(f"   ❌ Error respaldo: {str(e)}")
                    continue
        
        if st.session_state.get('debug_mode', False):
            st.write(f"📊 Método 5 encontró: {len(operaciones)} operaciones mínimas")
        
        return operaciones
    
    def _buscar_info_adicional(self, texto: str, match: re.Match) -> Tuple[str, float]:
        """Busca plazo e importe pendiente después en el contexto del match"""
        plazo = ""
        importe_pendiente_despues = 0.0
        
        # Contexto alrededor del match
        inicio = max(0, match.start() - 50)
        fin = min(len(texto), match.end() + 300)
        contexto = texto[inicio:fin]
        
        # Buscar plazo
        plazo_match = re.search(r'Plazo\s+(\d+\s*De\s*\d+)', contexto, re.IGNORECASE)
        if not plazo_match:
            plazo_match = re.search(r'PRÓXIMO\s*PLAZO\s*(\d{2}-\d{2}-\d{4})', contexto, re.IGNORECASE)
        if plazo_match:
            plazo = plazo_match.group(1)
        
        # Buscar importe pendiente después
        pendiente_match = re.search(r'Importe\s+pendiente\s+después.*?(\d+[,\.]\d{2})', contexto, re.IGNORECASE)
        if pendiente_match:
            try:
                importe_pendiente_despues = float(pendiente_match.group(1).replace(',', '.'))
            except ValueError:
                pass
        
        return plazo, importe_pendiente_despues
    
    def _buscar_info_lineas_siguientes(self, lineas: List[str], indice_actual: int) -> Tuple[str, float]:
        """Busca información adicional en las líneas siguientes"""
        plazo = ""
        importe_pendiente_despues = 0.0
        
        # Revisar las siguientes 6 líneas
        for j in range(indice_actual + 1, min(indice_actual + 7, len(lineas))):
            if j >= len(lineas):
                break
            
            linea_siguiente = lineas[j].strip()
            
            # Buscar plazo
            if not plazo:
                plazo_match = re.search(r'Plazo\s+(\d+\s*De\s*\d+)', linea_siguiente, re.IGNORECASE)
                if not plazo_match:
                    plazo_match = re.search(r'PRÓXIMO\s*PLAZO\s*(\d{2}-\d{2}-\d{4})', linea_siguiente, re.IGNORECASE)
                if plazo_match:
                    plazo = plazo_match.group(1)
            
            # Buscar importe pendiente después
            if "pendiente después" in linea_siguiente.lower():
                pendiente_match = re.search(r'(\d+[,\.]\d{2})', linea_siguiente)
                if pendiente_match:
                    try:
                        importe_pendiente_despues = float(pendiente_match.group(1).replace(',', '.'))
                    except ValueError:
                        pass
        
        return plazo, importe_pendiente_despues
    
    def _eliminar_duplicados(self, operaciones: List[Dict]) -> List[Dict]:
        """Elimina operaciones duplicadas basándose en fecha e importe"""
        operaciones_unicas = []
        
        for operacion in operaciones:
            es_duplicado = any(
                op['fecha'] == operacion['fecha'] and 
                abs(op['importe_operacion'] - operacion['importe_operacion']) < 0.01
                for op in operaciones_unicas
            )
            
            if not es_duplicado:
                operaciones_unicas.append(operacion)
        
        return operaciones_unicas
    
    def _mostrar_resumen_debug(self, operaciones: List[Dict], pdf_id: str):
        """Muestra un resumen detallado del debug"""
        st.write(f"🎯 **RESUMEN FINAL - {pdf_id}**")
        st.write(f"   📊 Total operaciones encontradas: {len(operaciones)}")
        
        if operaciones:
            # Agrupar por método de extracción
            metodos = {}
            for op in operaciones:
                metodo = op.get('metodo_extraccion', 'desconocido')
                if metodo not in metodos:
                    metodos[metodo] = 0
                metodos[metodo] += 1
            
            st.write("   📈 Por método de extracción:")
            for metodo, cantidad in metodos.items():
                st.write(f"      - {metodo}: {cantidad} operaciones")
            
            st.write("   📋 **Todas las operaciones encontradas:**")
            for i, op in enumerate(operaciones, 1):
                metodo = op.get('metodo_extraccion', 'N/A')
                st.write(f"      {i}. {op['fecha']} - {op['concepto']} - {op['importe_operacion']}€ - Método: {metodo}")
                if op.get('plazo'):
                    st.write(f"         └─ Plazo: {op['plazo']}")
        else:
            st.error("❌ **NO SE ENCONTRARON OPERACIONES FRACCIONADAS**")
            st.write("🔍 **Sugerencias de diagnóstico:**")
            st.write("   • Verificar si el PDF tiene la estructura esperada")
            st.write("   • Comprobar si hay problemas en la extracción de texto")
            st.write("   • Revisar si el formato es diferente al esperado")

# Función principal que se importará desde main.py
def extraer_operaciones_fraccionadas_avanzado(texto: str, pdf_id: str = "default") -> List[Dict]:
    """
    Función principal para extraer operaciones fraccionadas.
    Esta función será llamada desde main.py
    """
    extractor = ExtractorOperacionesFraccionadas()
    return extractor.extraer_operaciones_fraccionadas(texto, pdf_id)

# Para testing independiente
if __name__ == "__main__":
    # Código de prueba si se ejecuta este módulo directamente
    print("Módulo de operaciones fraccionadas - v2.6")
    print("Para usar, importar desde main.py")
