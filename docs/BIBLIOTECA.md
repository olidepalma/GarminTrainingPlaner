# Biblioteca de entrenamiento

La pestaña **Biblioteca** guarda documentos privados en `GTP_DATA_DIR/library` y sus versiones, metadatos y fragmentos en SQLite. Todo está fuera de Git. Las rutas de consulta, muestras, subida, selección y procesamiento requieren la sesión del panel; las modificaciones requieren CSRF y origen válido.

## Uso

1. Selecciona **Nueva fuente**, añade título y autor opcionales y sube un EPUB, PDF, DOCX, TXT o Markdown (hasta 40 MB). Para referencias propias, puedes preparar un TXT o Markdown con texto y enlaces de procedencia. Los enlaces no se descargan automáticamente.
2. Pulsa **Procesar documento**. La extracción y la indexación ocurren en el servidor local, sin OpenAI ni embeddings externos. Revisa **Ver muestra** antes de usarlo.
3. Marca **Usar en el coach**. Seleccionar una fuente no genera una planificación.
4. En Coach y objetivos, pulsa **Generar borrador**. La búsqueda local FTS5 utiliza vocabulario deportivo español/inglés para recuperar hasta seis fragmentos (1.200 caracteres cada uno, 7.200 en total). Es búsqueda léxica: puede omitir información relevante y no equivale a leer ni interpretar el libro completo.
5. El borrador muestra los fragmentos enviados, versión y sección/página, y distingue cuáles citó el modelo. La planificación conserva esta instantánea incluso si se actualiza o desactiva después la fuente.

## Actualizar una fuente

Elige la fuente existente en el selector y sube el nuevo archivo. Se crea otra versión pendiente y se mantiene la anterior activa. **Procesar actualización** sustituye la versión activa solo cuando la extracción y la indexación terminan correctamente. Un fallo conserva la versión anterior; todas las versiones y sus fragmentos permanecen disponibles internamente para auditoría. Cambiar una fuente no modifica planes ya generados o aceptados.

## Formatos y límites

EPUB suele ser preferible para libros: se sigue el orden de lectura y se conserva el título de la sección y su archivo como localizador, sin inventar páginas. PDF conserva el número de página, pero necesita texto seleccionable; no incluye OCR. DOCX conserva texto de párrafos y tablas, sin maquetación. TXT y Markdown deben estar en UTF-8. No se interpretan figuras, fórmulas gráficas ni tablas complejas; consulta el original cuando sean esenciales. No se admite contenido cifrado o con DRM ni se elimina protección.

Los archivos ZIP se leen sin extraer rutas al disco, con límites de miembros y tamaño expandido; los PDF tienen límites de páginas y complejidad. No se ejecuta HTML, scripts ni contenido de los documentos. Los extractos son contexto, no instrucciones para el coach. Solo los fragmentos elegidos se envían a OpenAI al generar: subir y procesar no consume Pro. No hay actualización o regeneración semanal automática.

La identidad de una cita se valida contra los fragmentos enviados; la fidelidad de la interpretación y la calidad de la planificación requieren revisión. Por ahora no hay eliminación de fuentes en la interfaz: desmárcalas para excluirlas de generaciones futuras. Para copias de seguridad, conserva tanto la carpeta de documentos como SQLite y los secretos existentes del proyecto.
