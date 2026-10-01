# Propuesta de producto y arquitectura

Fecha de consulta: 30 de septiembre de 2026. Documento de diseño, no especificación de una aplicación ya implementada.

Actualización tras la elección de la usuaria: ChatGPT Pro como proveedor y LXC de Proxmox como destino. Desarrollo nativo en Windows/macOS con Python 3.12 y uv, descrito en [DESARROLLO.md](DESARROLLO.md). Las recomendaciones iniciales de VM/Docker y alternativas de API de este documento quedan como contexto, no como decisiones vigentes. La API de pago no se activará como fallback.

## Recomendación

Construir una aplicación propia con backend Python, interfaz React/TypeScript y PostgreSQL, desplegable mediante Docker Compose. El backend realizará sincronización, cálculos, autorización y validación del plan. Un worker con trabajos persistidos ejecutará las tareas nocturnas y de planificación sin bloquear la web. Para uso personal no hace falta incorporar Redis o una arquitectura de microservicios inicialmente.

En Proxmox, una VM Debian con Docker Compose es la opción propuesta para aislar el despliegue. Si se prefiere LXC, comprobar primero la configuración y el soporte del entorno para ejecutar Docker. El reverse proxy existente puede proporcionar HTTPS; Caddy es una alternativa si no hay uno. Mantener PostgreSQL y worker sin puertos públicos.

## Producto

- Login propio, registro público cerrado y posibilidad futura de usuarios invitados.
- Panel de estadísticas por deporte, evolución semanal, adherencia y estado de sincronización.
- Calendario con competiciones, sesiones planificadas y actividades realizadas.
- Un único objetivo principal activo, con fecha exacta, disciplina, distancia y desnivel cuando corresponda. Competiciones secundarias que también condicionan el calendario.
- Disponibilidad por día y minutos, presupuesto semanal de horas, días de descanso y posibilidad de dobles sesiones.
- Día preferido de tirada larga de carrera y día de salida larga de bici por separado.
- Acceso a piscina, longitud de piscina, material, rodillo y gimnasio.
- Fuerza opcional, experiencia, preferencias, limitaciones declaradas y zonas/umbrales por deporte con fecha y procedencia.
- Editor manual de sesiones con calentamiento, bloques, repeticiones, recuperación y vuelta a la calma. Fuerza con ejercicios, series, repeticiones, descanso y material.
- Estados de sesión: propuesta, aceptada, realizada, omitida y sustituida. Una actividad realizada no es una sesión futura.
- Asociación sugerida entre actividad y sesión, corregible manualmente, contemplando entrenamientos divididos y sesiones de transición de triatlón.
- Bloqueo de sesiones editadas o creadas manualmente para conservarlas durante la revisión del plan.
- Valoración rápida de esfuerzo percibido, fatiga, molestias y motivo de sesiones omitidas.

## Garmin: alcance y limitaciones

El [programa oficial](https://developer.garmin.com/gc-developer-program/program-faq/) está orientado a uso empresarial y requiere aprobación. No basar el proyecto personal en conseguir ese acceso.

Probar primero [python-garminconnect](https://github.com/cyberjunky/python-garminconnect). Es un cliente no oficial: su documentación actual describe autenticación con MFA, persistencia y renovación de tokens, lectura de datos y creación/programación de workouts. La disponibilidad debe verificarse con la cuenta y el reloj reales. No desactivar MFA. Mantener la integración detrás de un adaptador para poder sustituirla.

Flujo propuesto:

1. Autenticación inicial privada con MFA cuando se solicite; conservar tokens protegidos fuera de Git.
2. Importación inicial configurable; proponer 90 días para empezar, ampliable después sin llamadas a IA.
3. Trabajo nocturno, por ejemplo 03:00 Europe/Madrid, con botón de sincronización manual.
4. Identificar actividades por usuario e ID Garmin; insertar o actualizar sin duplicados. Guardar progreso solo tras persistir los datos.
5. Revisar una ventana reciente configurable para actividades tardías, ediciones y métricas de bienestar que se completan después. Permitir reconciliación histórica bajo demanda; un marcador temporal por sí solo no detecta todos los cambios o borrados.
6. Sincronizar actividades y bienestar con cursores independientes, reintentos limitados, espera ante límites y exclusión de trabajos simultáneos sobre la misma cuenta.
7. Mostrar última sincronización correcta, cobertura, datos desactualizados y necesidad de reautenticación. No recalcular planes sobre datos incompletos sin avisar.

Guardar unidades, fechas originales y procedencia. Conservar una copia privada del dato original cuando sea útil para recalcular; nunca servirla desde una carpeta pública. Descarga de streams/GPS solo bajo demanda cuando aporte valor.

## Coach y uso de ChatGPT Pro

Separar el método de entrenamiento del proveedor de IA. Una skill puede aportar instrucciones y referencias, pero requiere un runtime que la ejecute; el botón de la web debe llamar a un servicio de planificación del backend.

Tres vías posibles:

- **Sign in with ChatGPT:** la [documentación oficial](https://developers.openai.com/siwc/quickstart) describe uso del plan de usuarios Plus/Pro elegibles en clientes open source y determinados clientes privados. Estudiar elegibilidad/registro de este proyecto; un repositorio Git privado no equivale a ser open source. Existe una [guía para VM propia](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms). Está en preview y tiene [restricciones de peticiones y herramientas](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations); comprobar especialmente formato estructurado, modelos disponibles y límites. No garantizar acceso antes de probarlo. No emplear cookies de ChatGPT ni credenciales prestadas de otro cliente.
- **API OpenAI con clave propia:** vía alternativa para una integración autónoma; consumo facturado conforme a los [precios de API](https://developers.openai.com/api/docs/pricing), separado de la suscripción. Credenciales solo en backend. El modelo será configurable y se elegirá mediante evaluación de planes.
- **Intercambio manual:** exportar un resumen compacto para usar en ChatGPT e importar una respuesta estructurada validada. Útil mientras se valida la integración Pro y para mantener el calendario independiente del proveedor.

Implementar proveedores intercambiables; ningún cambio de ruta debe activar gasto adicional de API silenciosamente. MCP puede añadirse después para consultar resúmenes y proponer planes desde ChatGPT; no es necesario para la primera web.

## Horizonte y adaptación

Crear una estructura general hasta la competición: fases, prioridades, semanas de recuperación y aproximación a la carrera. Concretar siete días y, opcionalmente, mostrar la semana posterior como provisional. Revisión semanal sobre lo realizado, evolución, restricciones nuevas y fase actual; conservar la continuidad y las decisiones anteriores.

La calidad dependerá de un método explícito, catálogo de sesiones y controles externos al modelo. No delegar toda la lógica deportiva en un prompt. Versionar las reglas y revisar sus fuentes antes de prescribir parámetros concretos. Los repositorios de referencia no demuestran eficacia clínica ni validan automáticamente sus planes.

El modelo propone sesiones y explica cambios; el backend comprueba fechas, unidades, suma de bloques, disponibilidad, presupuesto de tiempo, deportes permitidos, objetivos, sesiones bloqueadas y reglas de progresión/recuperación configuradas. Un JSON válido no garantiza un entrenamiento adecuado.

Separar carga por disciplina y documentar la métrica usada. No presentar estimaciones como valores Garmin ni equiparar automáticamente cargas de fuerza, natación, carrera y ciclismo. No inventar FTP, ritmo umbral, CSS o zonas ausentes; solicitar calibración o usar objetivos de esfuerzo claramente etiquetados.

Sueño, HRV, pulso en reposo y otras métricas disponibles se habilitan por separado. Comparar con el historial personal y mostrar cobertura; dato ausente no significa recuperación buena ni mala. Usar tendencias como señales para revisión, junto con sensaciones declaradas. Evitar que una lectura aislada cambie todo el programa. Molestias o enfermedad declaradas deben activar revisión conservadora, sin generar diagnósticos o rehabilitación automática.

Proponer avisos visibles en la web por sincronización fallida, baja cobertura, incompatibilidad de disponibilidad o señales de fatiga configuradas. Replanificación semanal como borrador revisable; ajustes diarios opcionales y acotados a las próximas sesiones. No desplazar el entrenamiento omitido automáticamente al día siguiente.

## Consumo moderado

Calcular localmente estadísticas y resumen. Enviar únicamente:

- Perfil deportivo y restricciones relevantes.
- Objetivo principal, fase y competiciones próximas.
- Últimos siete a catorce días resumidos por sesión.
- Agregados semanales de ocho a doce semanas para tendencias y continuidad.
- Resumen de recuperación opcional con cobertura y procedencia.
- Plan vigente, sesiones bloqueadas y breve registro estructurado de decisiones.

El histórico completo permanece local. Sin streams segundo a segundo, rutas GPS, credenciales ni conversaciones acumuladas dentro del prompt. Recuperar detalle adicional solo cuando sea necesario.

Como presupuesto inicial de ingeniería, apuntar a 3.000–6.000 tokens de contexto y 1.000–3.000 de respuesta, sujeto a medición; no son cuotas ni precios garantizados. Una generación semanal habitual y regeneración cuando cambien datos/restricciones. Persistir planes y usar una huella de entradas, versión de método y modelo para evitar repetir llamadas idénticas.

Registrar uso real, incluyendo razonamiento cuando se reporte, latencia, motivo y coste en modo API. Añadir presupuesto mensual aplicado por la app, reserva para trabajos concurrentes y límite de reintentos. En la ruta Pro respetar las restricciones de preview: no asume soporte de max_output_tokens ni caché garantizada entre semanas. Un resumen excesivamente pequeño también puede reducir calidad; evaluar el equilibrio.

## Sesiones en el Fenix 7S

La [Training API oficial](https://developer.garmin.com/gc-developer-program/training-api/) publica workouts y planes en Garmin Connect, con sincronización a dispositivos compatibles, pero requiere aprobación.

Para uso personal, probar el adaptador no oficial con una sesión sencilla de carrera, luego ciclismo, natación y fuerza. Verificar creación, programación, aparición en el reloj y objetivos/unidades. Mantener IDs remotos y versión/hash para evitar duplicados; actualizar sesiones futuras sin sobrescribir actividades realizadas. La usuaria decide qué sesiones enviar.

Ofrecer exportación FIT de tipo workout solo tras verificar su compatibilidad. No confundir importar una actividad realizada o un recorrido con importar una sesión estructurada futura en Garmin Connect. La subida genérica de archivos no debe anunciarse como solución garantizada. La alternativa manual inicial es recrear los bloques en el editor de entrenamientos de Garmin Connect y enviarlos al dispositivo. Validar aparte una posible transferencia FIT directa al reloj.

## Seguridad, datos y despliegue

Login con sesiones HttpOnly/Secure, defensa CSRF, contraseñas con hash robusto si hay login local y límites de intentos. Autorizar cada lectura/escritura por usuario en backend; incluir archivos, exportaciones y trabajos. Registro cerrado y sin credenciales predeterminadas.

Tokens Garmin/OpenAI y datos originales en almacenamiento privado protegido. Si se cifran secretos en base de datos, mantener la clave fuera de la base y documentar su backup independiente. Evitar tokens, rutas, salud y respuestas completas en logs. Enviar al proveedor solo datos pertinentes con controles de inclusión; documentar qué sale del servidor.

Docker Compose, migraciones, versiones de dependencias fijadas, .env.example sin secretos y instrucciones para reverse proxy. Copias de base de datos y volúmenes, prueba de restauración y healthchecks de web, worker y sincronización. Zona de calendario Europe/Madrid y persistencia temporal coherente con cambios de hora.

Entidades propuestas: usuarios, conexiones, actividades, métricas diarias, zonas/umbrales, disponibilidad, objetivos/eventos, sesiones/plantillas, versiones del plan, feedback, asociaciones actividad-sesión, trabajos, ejecuciones de sync y uso de IA. Restricción de un objetivo principal activo y claves de idempotencia por usuario.

## Referencias revisadas

| Recurso | Aporte posible | Diferencia con este proyecto |
| --- | --- | --- |
| [garming-stats](https://github.com/RafaTatay/garming-stats) | Panel e importación incremental | Guarda JSON en public/data y ajustes en navegador; requiere cambiar persistencia y privacidad para una URL con login |
| [adaptive-endurance-coach](https://github.com/mprecilio20/adaptive-endurance-coach) | Periodización, memoria y registro de decisiones | Usa TrainingPeaks como fuente principal; no proporciona nuestra web ni integración directa Garmin |
| [endurance-coach-skill](https://github.com/shiv19/endurance-coach-skill) y [demo](https://shiv19.com/endurance-coach-skill/) | Editor y exportaciones de sesiones | Su README describe datos en navegador y conexión Strava; estudiar ideas y exportadores, no asumir backend privado |
| [intervals-mcp-server](https://github.com/mvilanova/intervals-mcp-server) | Herramientas MCP de actividades, bienestar y eventos | Conecta con Intervals.icu; incorporarlo añadiría otro servicio. El repo declara GPL-3.0 |

La revisión ha sido de documentación pública, no una auditoría de código. Revisar licencias antes de reutilizar código. No ejecutar instrucciones de instalación de terceros como parte de este análisis.

## Fases y criterios de aceptación

1. **Pruebas de integraciones:** login Garmin con MFA, descarga de actividades/bienestar disponible, dos sincronizaciones sin duplicados y prueba Pro/elegibilidad o elección de API/manual. Subida de una sesión de prueba solo cuando la usuaria autorice la escritura en Garmin.
2. **Base privada desplegable:** login, PostgreSQL, migraciones, Compose, sincronización nocturna y panel. Acceso anónimo denegado también a los datos/exportaciones; aislamiento entre usuarios verificado.
3. **Calendario y editor:** objetivos, disponibilidad, sesiones manuales, bloqueos y asociación con actividades. Cambios persistentes entre dispositivos y reinicios.
4. **Coach semanal:** contexto compacto, proveedor, catálogo/método versionado, validadores, propuestas y comparación de versiones. Presupuesto y uso visibles.
5. **Integración con reloj:** formatos y deportes comprobados con Fenix 7S, envío selectivo, programación y control de duplicados.
6. **Operación:** backup/restauración, fallos de autenticación, reintentos, logs sin secretos, documentación de actualización y despliegue.

Evaluar el coach con casos de referencia: triatlón sprint con fuerza, trail con desnivel, semana sin piscina, menor disponibilidad, datos ausentes, fatiga declarada y sesiones manuales bloqueadas. Medir cumplimiento de restricciones, coherencia de unidades/duración, continuidad, explicaciones y calidad deportiva revisada por una persona competente. Verificar que una respuesta inválida deja intacto el plan aceptado y que una regeneración concurrente no lo sustituye accidentalmente.

## Decisiones pendientes

- Uso exclusivamente personal o varios usuarios invitados.
- Proyecto privado o publicación open source, relevante para Sign in with ChatGPT.
- Preferencia por validar primero Pro o empezar con API y presupuesto explícito.
- VM o LXC y reverse proxy existente.
- Primera competición con fecha exacta; marzo de 2027 sería una hipótesis, no un objetivo confirmado.

No hacen falta contraseñas o datos personales en el chat para resolver estas decisiones.
