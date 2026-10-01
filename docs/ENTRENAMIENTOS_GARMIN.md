# Sesiones por bloques y Garmin Connect

En Calendario, pulsa **Crear sesión**. Elige fecha, deporte y duración; añade calentamiento, ejercicio, recuperación, descanso, vuelta a la calma o grupos repetidos. Puedes ordenar los bloques y definir tiempos en minutos:segundos, metros, pulsación de Lap o repeticiones de fuerza. Los objetivos admiten zonas de pulso y, en ciclismo, potencia.

Guardar añade una propuesta privada al calendario, junto al coach y las actividades realizadas. Abre su detalle y pulsa **Revisar envío a Garmin**. Comprueba fecha y bloques antes de **Crear y programar en Garmin Connect**; después sincroniza el reloj con Connect. El envío no llama a OpenAI.

Las nuevas generaciones del coach incluyen bloques editables en el borrador. Las sesiones antiguas con solo texto necesitan una copia y revisión manual: los bloques iniciales son una plantilla, no una traducción del texto. Crear una copia añade otra propuesta; el coach incluye las sesiones propias de la semana en el volumen y la disponibilidad.

Natación admite longitud de piscina, estilo, material y notas por bloque. Se han verificado en sesiones nativas los identificadores de crol, espalda, braza, estilo libre de elección, tabla y pull buoy. Materiales y estilos aún no verificados se conservan como notas y se avisa antes del envío. Las distancias deben ser múltiplos de la piscina; no se exportan objetivos de intensidad para natación. Trail se exporta como carrera.

La integración usa python-garminconnect y sus endpoints no oficiales. La compatibilidad final depende de Garmin y del dispositivo. No se modifica automáticamente una sesión publicada: crea una variante. Se guarda el identificador remoto para evitar duplicados. Si Garmin responde de forma incierta, comprueba tu cuenta: no se reenvía automáticamente y hace falta resolver ese estado antes de volver a publicar. No se eliminan entrenamientos remotos desde esta web.

La duración estimada es independiente de la suma de los bloques. Si difieren se muestra un aviso, pero se permite guardar y enviar. Los tiempos se conservan internamente y se envían a Garmin en segundos; los bloques y la estimación no se reajustan automáticamente.

En el detalle de una sesión propia o del coach, **Borrar sesión** abre una confirmación. Cancelar conserva la sesión; confirmar la quita del calendario local y del volumen planificado. Los borradores se actualizan sin alterar el histórico aceptado. Se conserva un registro local del borrado y de los envíos. Las sesiones enviadas siguen en Garmin Connect y en el reloj; el borrado remoto se realiza allí. Las actividades realizadas procedentes de Garmin no se borran desde este botón.
