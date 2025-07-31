"""
Módulo especializado para extraer operaciones fraccionadas de extractos bancarios.
Enfocado en resolver problemas específicos de formato y patrones.

Versión 2.7 - Lógica de búsqueda de plazo unificada
"""

import re
import streamlit as st
from typing import List, Dict, Optional, Tuple

class ExtractorOperacionesFraccionadas:
    """Clase especializada en extraer operaciones fraccionadas con múltiples estrategias"""
    
    def __init__(self):
        # Patrones optimizados para diferentes formatos de CaixaBank
        self.patrones_caixabank = {
            'tabla_estandar': r'(\d{2}\.\d{2}\.\d{4})\s+CAJ\.LA\s*CAIXA\s+(?:OF\.\d{4})?\s*(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})\s+(\d+[,\.]\d{2})',
            'linea_flexible': r'(\d{2}\.\d{2}\.\d{4}).*?(?:CAJ\.LA\s*CAIXA|B\.B\.V\.A\.).*?(\d+[,\.]\d{2})'
        }
    
    def extraer_operaciones_fraccionadas(self, texto: str, pdf_id: str = "default") -> List[Dict]:
        """
        Método principal que coordina todos los enfoques de extracción.
        Ahora utiliza una única estrategia robusta de línea por línea.
        """
        operaciones = []
        
        if st.session_state.get('debug_mode', False):
            st.write(f"🔧 **MÓDULO ESPECIALIZADO FRACCIONADAS** - PDF: {pdf_id}")
        
        # Estrategia unificada: analizar línea por línea todo el texto
        seccion_fraccionadas = self._buscar_seccion_fraccionadas(texto)
        texto_a_procesar = seccion_fraccionadas if seccion_fraccionadas else texto

        lineas = texto_a_procesar.split('\n')
        for i, linea in enumerate(lineas):
            linea = linea.strip()
            
            # Buscar una línea que sea candidata a ser una operación fraccionada
            match_candidato = re.search(self.patrones_caixabank['linea_flexible'], linea)
            
            if match_candidato:
                if st.session_state.get('debug_mode', False):
                    st.write(f"  🔍 Línea candidata {i+1}: {linea}")
                
                try:
                    fecha = match_candidato.group(1)
                    
                    # Extraer todos los números de la línea para determinar los importes
                    numeros_en_linea = re.findall(r'\d+[,\.]\d{2}', linea)
                    if not numeros_en_linea:
                        continue

                    numeros_float = [float(n.replace(',', '.')) for n in numeros_en_linea]
                    
                    # CORRECCIÓN: Buscar siempre la información adicional en el contexto
                    plazo, importe_pendiente_despues = self._buscar_info_adicional(texto, i)

                    concepto = "B.B.V.A." if "B.B.V.A." in linea else "CAJ.LA CAIXA"

                    operacion = {
                        'fecha': fecha,
                        'concepto': concepto,
                        'importe_operacion': numeros_float[0],
                        'importe_pendiente': numeros_float[1] if len(numeros_float) > 1 else numeros_float[0],
                        'capital_amortizado': numeros_float[2] if len(numeros_float) > 2 else 0.0,
                        'intereses': numeros_float[3] if len(numeros_float) > 3 else 0.0,
                        'cuota_mensual': numeros_float[4] if len(numeros_float) > 4 else 0.0,
                        'plazo': plazo,
                        'importe_pendiente_despues': importe_pendiente_despues,
                        'metodo_extraccion': 'linea_unificada'
                    }
                    operaciones.append(operacion)

                    if st.session_state.get('debug_mode', False):
                        st.write(f"    ✅ Op: {fecha} - {operacion['importe_operacion']}€ - Plazo: '{plazo}'")

                except (ValueError, IndexError) as e:
                    if st.session_state.get('debug_mode', False):
                        st.write(f"    ❌ Error procesando línea {i+1}: {e}")
                    continue

        # Eliminar duplicados al final
        operaciones = self._eliminar_duplicados(operaciones)
        
        if st.session_state.get('debug_mode', False):
            self._mostrar_resumen_debug(operaciones, pdf_id)
            
        return operaciones

    def _buscar_seccion_fraccionadas(self, texto: str) -> Optional[str]:
        """Busca y devuelve la sección de operaciones fraccionadas si existe."""
        patron_seccion = r'IMPORTE OPERACIONES FRACCIONADAS(.*?)(?=OPERACIONES DE LA TARJETA|TOTAL OPERACIONES|$)'
        match = re.search(patron_seccion, texto, re.DOTALL | re.IGNORECASE)
        if match:
            if st.session_state.get('debug_mode', False):
                st.write("✅ Sección fraccionadas encontrada.")
            return match.group(1)
        if st.session_state.get('debug_mode', False):
            st.write("⚠️ No se encontró sección específica de fraccionadas, se usará el texto completo.")
        return None

    def _buscar_info_adicional(self, texto_completo: str, indice_linea_actual: int) -> Tuple[str, float]:
        """
        Busca plazo e importe pendiente después en el contexto de la línea actual.
        Analiza la línea actual y las 5 siguientes.
        """
        plazo = ""
        importe_pendiente_despues = 0.0
        lineas = texto_completo.split('\n')
        
        # Definir el rango de líneas a escanear (la actual + 5 siguientes)
        rango_escaneo = range(indice_linea_actual, min(indice_linea_actual + 6, len(lineas)))

        for i in rango_escaneo:
            linea = lineas[i].strip()
            
            # Buscar plazo (solo si aún no se ha encontrado)
            if not plazo:
                # Prioridad 1: "Plazo X De Y"
                plazo_match = re.search(r'Plazo\s+(\d+\s*De\s*\d+)', linea, re.IGNORECASE)
                if plazo_match:
                    plazo = plazo_match.group(1)
                else:
                    # Prioridad 2: "PROXIMO PLAZO DD-MM-YYYY"
                    plazo_match = re.search(r'PRÓXIMO\s*PLAZO\s*(\d{2}-\d{2}-\d{4})', linea, re.IGNORECASE)
                    if plazo_match:
                        plazo = plazo_match.group(1)

            # Buscar importe pendiente después
            if "pendiente después" in linea.lower():
                pendiente_match = re.search(r'(\d+[,\.]\d{2})', linea)
                if pendiente_match:
                    try:
                        importe_pendiente_despues = float(pendiente_match.group(1).replace(',', '.'))
                    except ValueError:
                        pass
        
        return plazo.strip(), importe_pendiente_despues

    def _eliminar_duplicados(self, operaciones: List[Dict]) -> List[Dict]:
        """Elimina operaciones duplicadas basándose en fecha e importe de operación."""
        operaciones_unicas = []
        vistos = set()
        for operacion in operaciones:
            # Crear una tupla identificadora para la operación
            identificador = (operacion['fecha'], operacion['importe_operacion'])
            if identificador not in vistos:
                operaciones_unicas.append(operacion)
                vistos.add(identificador)
        return operaciones_unicas

    def _mostrar_resumen_debug(self, operaciones: List[Dict], pdf_id: str):
        """Muestra un resumen detallado del debug."""
        st.write(f"🎯 **RESUMEN FINAL - {pdf_id}**")
        st.write(f"  📊 Total operaciones únicas encontradas: {len(operaciones)}")
        
        if operaciones:
            st.write("  📋 **Operaciones encontradas (con Plazo):**")
            for i, op in enumerate(operaciones, 1):
                plazo_info = f"Plazo: '{op.get('plazo', 'N/A')}'"
                st.write(f"    {i}. {op['fecha']} - {op['importe_operacion']}€ - {plazo_info}")
        else:
            st.error("❌ **NO SE ENCONTRARON OPERACIONES FRACCIONADAS**")

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
    st.info("Módulo de operaciones fraccionadas - v2.7. Para usar, importar desde main.py")
