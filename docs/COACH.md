# Coach multideporte

La sección **Coach y objetivos** permite elegir deportes disponibles, experiencia, zonas conocidas y preferencias. El triatlón exige habilitar carrera, ciclismo y natación. La fuerza es un complemento opcional. Cada día admite entre cero y cuatro franjas, con horario orientativo (mañana, mediodía, tarde, noche o flexible) y duración propia. Las sesiones deben asignarse a una franja y respetar sus minutos: 60 minutos por la mañana + 60 por la tarde no permiten una sesión continua de 120. Una transición de bici y carrera puede compartir una franja. Los minutos disponibles de lunes a domingo se suman entre todas las sesiones del día; el máximo de días incluye sesiones dobles como un único día. Las tiradas largas de carrera/trail y bici tienen días preferentes independientes.

Cada prueba guarda fecha, modalidad, distancias, resultado deseado y prioridad. Solo puede haber un objetivo principal; las secundarias deben integrarse en la estrategia sin convertirse automáticamente en picos equivalentes. El selector ofrece 5/10/15 km, media maratón y maratón para carrera; sprint, olímpico, 70.3 y 140.6 para triatlón, y varias distancias de natación. El servidor resuelve la distancia del catálogo, incluso si el navegador envía otro texto. Para trail, ciclismo o pruebas con distancias especiales, usa Otra / personalizada.

## Flujo

1. Consulta los modelos con tu cuenta Pro. Elige uno para la estructura inicial y otro para los ajustes semanales. No hay cambios de modelo ni API de pago automáticos cuando una petición falla.
2. Guarda el perfil y los objetivos. Elige el primer día entre hoy y los próximos 28 días, con el objetivo principal pendiente.
3. Genera un borrador: estructura textual hasta la competición principal y sesiones detalladas durante siete días. Las transiciones se representan con sesiones enlazadas de bici y carrera en la misma fecha.
4. Revisa y edita estrategia, explicación, fechas, deporte, intensidad, duración e indicaciones; añade o elimina sesiones.
5. Guarda la semana revisada. **Reemplaza las sesiones planificadas de esos siete días**, conservando otras semanas y el historial Garmin. Regenerar por sí solo no modifica el calendario. No hay todavía editor independiente del calendario aceptado.
6. Tras sincronizar el progreso, solicita el ajuste semanal. La generación siempre es manual y consume uso del plan Pro. No se realiza una nueva llamada a OpenAI al aceptar o editar.

## Referencias Garmin

La sincronización consulta zonas de pulsaciones, zonas de potencia, FTP de ciclismo, FC de umbral, pronósticos de carrera y VO₂ máx. de los últimos 30 días. La pestaña **Estadísticas Garmin** muestra los campos reconocidos, sus fechas si Garmin las proporciona y el estado de descarga. Los fallos no borran datos anteriores. Un formato desconocido se identifica expresamente; no significa ausencia de la métrica en tu reloj. No se consultan Garmin ni OpenAI al abrir esta pestaña: muestra la copia local.

El coach recibe automáticamente FC, zonas de potencia, FTP, umbral, los dos últimos registros de VO₂ por perfil y pronósticos si activas **Incluir las estadísticas Garmin**. El campo manual sirve para correcciones o datos ausentes. Los pronósticos se incluyen como estimaciones, nunca como ritmos obligatorios. Las zonas de potencia y velocidades de umbral con unidad no confirmada no se convierten ni se usan como referencias de intensidad.

La extracción guarda solo campos deportivos seleccionados, sin identificadores de perfil ni datos personales de las respuestas originales. La compatibilidad depende de los campos devueltos por Garmin; está comprobada con respuestas simuladas, pendiente de verificar con las métricas de tu cuenta real.

Al guardar un perfil antiguo, su disponibilidad se presenta inicialmente como una franja flexible por día. Puedes dividirla antes de guardar. Los borradores anteriores al cambio del perfil necesitan regeneración; el historial y el calendario existente se conservan.

## Contexto y controles

Se calculan localmente seis resúmenes de siete días terminados en la fecha actual: sesiones, minutos, distancia y desnivel por deporte. No se envían nombres de actividades, recorridos ni todo el historial. Se envía además perfil, objetivos y última estrategia aceptada con resumen de sesiones. Es la misma memoria para ambos modelos; no depende de memoria de conversaciones de ChatGPT.

La recuperación es opcional y se envía únicamente si se activa en el perfil; sueño y HRV requieren también la preferencia de descarga correspondiente. Los valores ausentes no se inventan.

Se valida el formato, los deportes habilitados, la fuerza opcional, las fechas, el tiempo total por día, el número de días y los días elegidos para sesiones marcadas largas. Los errores impiden guardar. Días intensos consecutivos, disciplinas ausentes en triatlón y aumentos superiores al 20 % frente a los últimos siete días generan alertas de revisión, no reglas fisiológicas universales. La calidad deportiva de los planes requiere revisión: las validaciones no certifican la idoneidad del entrenamiento.

Se conserva el modelo, el uso comunicado por OpenAI y el tamaño del contexto. No hay reintentos de inferencia automáticos. La Biblioteca aporta hasta seis fragmentos seleccionados por búsqueda local, con un máximo de 7.200 caracteres de texto, versiones y localizadores. La petición separa las instrucciones del coach del contexto mediante mensajes developer/user. El servidor rechaza IDs de citas que no se enviaron; esto valida la procedencia, no certifica que cada interpretación del modelo sea correcta. Revisa las citas y sus extractos en el borrador.

Datos persistentes: `coach_setup`, `coach_draft`, `coach_accepted` y `coach_calendar` en SQLite dentro de `GTP_DATA_DIR`. No se guardan en Git. Las pruebas automatizadas usan un proveedor simulado y no consumen Pro.

## Calendario y tendencias

La pestaña Calendario reúne actividades realizadas de Garmin, sesiones aceptadas y competiciones principales/secundarias. Los deportes tienen iconos y colores propios, con estado textual visible. Navega por meses o vuelve al mes actual; al pulsar una entrada se abre su detalle (indicaciones de sesiones, datos disponibles de Garmin o datos de la prueba). También puedes mostrar el borrador actual, identificado como Borrador y sin guardarlo en el calendario. Los borradores de perfiles anteriores no se muestran.

Las actividades y propuestas son entradas distintas: no se asume que cualquier actividad del mismo día equivale a completar una sesión. Los horarios solo se muestran si todavía se pueden asociar al perfil usado al aceptar; no se asignan horarios actuales a semanas antiguas.

La tarjeta de capacidad aeróbica muestra exclusivamente los dos últimos registros fechados de VO₂ máx. por perfil seleccionado, con diferencia y dirección. No compara carrera y ciclismo ni mezcla registros precisos y redondeados del mismo día. FTP y umbrales siguen disponibles para el coach aunque no se muestren en esa tarjeta.

La importación de pronósticos admite los campos Garmin time5K/time10K/timeHalfMarathon/timeMarathon y mantiene compatibilidad con las variantes anteriores. Una copia local marcada como formato no reconocido requiere nueva sincronización, ya que la respuesta original no se guarda. La interfaz distingue ausencia de datos, fallo de descarga y formato desconocido.

## Revisión semanal

La comparación usa los siete días completos anteriores a hoy; excluye el día en curso. Se agregan sesiones, minutos, distancia y desnivel registrados por disciplina y se comparan con las propuestas aceptadas en ese intervalo. No se emparejan automáticamente actividades ni se deduce cumplimiento individual. La variación de volumen usa la media de las últimas cuatro semanas **con registros de esa disciplina** y muestra cuántas aportan datos; no equivale a una tendencia de rendimiento ni a TSS. Semanas vacías pueden ser descanso o datos ausentes. Se comunica la última sincronización al modelo.

Puedes guardar cansancio (1–5), esfuerzo global (1–10) y observaciones de esa semana. La revisión actual y las últimas cuatro revisiones recientes entran en la siguiente generación; guardar o modificar estas notas no llama a OpenAI. El modelo debe explicar qué conserva, qué cambia y por qué prioriza una disciplina, considerando objetivos principal/secundarios y recuperación opcional. Los borradores guardan el resumen y las versiones de fuentes utilizados en ese momento. La última semana aceptada muestra sus referencias; las aceptaciones anteriores conservan su instantánea en la tabla SQLite coach_history, aunque todavía no hay un visor de ese historial en la interfaz.

## Perfil personal y fuerza detallada

Sexo, edad, peso y altura son opcionales y editables en Coach y objetivos. Se incluye el perfil vigente en cada generación; actualizarlo no reescribe planes aceptados. Indica experiencia específica en fuerza, material y cargas habituales (peso total o por mancuerna, repeticiones y dificultad). Las medidas corporales no se usan para deducir capacidad de fuerza.

Las nuevas sesiones de fuerza incluyen un listado de nombres, series, repeticiones o segundos, carga orientativa, descansos y técnica o alternativas. El borrador y el detalle del calendario muestran esa lista. Una generación de fuerza sin ejercicios concretos se rechaza, manteniendo compatible el histórico anterior. Los bloques Garmin deben reflejar el mismo listado en sus notas. Las cargas sin referencias se consideran orientativas; se prioriza ejecución controlada y margen de repeticiones, sin llegar al fallo.
