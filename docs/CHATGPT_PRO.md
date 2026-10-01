# Cuenta ChatGPT Pro

La aplicación utiliza autorización oficial del cliente propio con PKCE, state, nonce, validación del ID token y permisos de uso del plan. No reutiliza cookies ni credenciales de Codex y no implementa una API de pago alternativa.

Conecta desde **Conexiones**, usando el panel en `http://127.0.0.1:8000` (o el puerto configurado). Los modelos se consultan desde tu cuenta; la prueba de conexión envía una frase sin datos deportivos. El coach tiene preferencias independientes para estructura inicial y ajuste semanal.

Las llamadas a Responses se realizan con streaming y `store:false`. La continuidad del coach se gestiona localmente mediante resúmenes y decisiones aceptadas. Consulta [el flujo y los datos enviados](COACH.md). El consumo comparte los límites de tu plan Pro; no se presupone uso ilimitado.

Los tokens se cifran en `GTP_DATA_DIR/secrets`. La clave está en esa misma carpeta: protege frente a una exposición de la base de datos, pero copiar toda la carpeta proporciona tanto clave como credenciales. Protege también las copias de seguridad. En Windows se aplican los permisos heredados del sistema. Al desconectar se eliminan las credenciales locales y se intenta revocar el acceso remoto.

El flujo está en preview y su disponibilidad depende de los permisos de la cuenta. Documentación: [registro y acceso](https://developers.openai.com/siwc/token-sharing-open-source/sign-in), [modelos e inferencia](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference).

El retorno local no llega directamente al LXC remoto. La autorización se completa mediante túnel SSH; el uso normal del coach puede hacerse desde el dominio HTTPS. Consulta [despliegue y migración](LXC.md).
