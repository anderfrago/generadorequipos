# Comprobaciones de la migración

Verificado localmente el 8 de septiembre de 2026:

- Compilación de producción Angular 22 completada, sin errores ni advertencias.
- 13 pruebas de backend superadas: acceso y CSRF, permisos por clase, restricciones de Google mediante respuestas simuladas, propiedad y revocación de enlaces, rotación de clave, validación y envío de cuestionarios, reapertura, relaciones entre alumnos, equipos y bloqueos, exportación y retirada/reincorporación de alumnado.
- Comparación con `GroupingEngine.gs`: 25 propuestas sintéticas y 75 equipos. Coinciden los cinco componentes y los índices, con tolerancia de redondeo de 0,1 puntos.
- Navegador Chrome: pantalla inicial, alumnado, generación y validación de equipos; cuestionario completo en anchura móvil de 390 píxeles, sin errores JavaScript ni desbordamiento horizontal.
- PDF individual, docente de equipos y de alumnado generados y revisados visualmente con datos ficticios.

La prueba del callback de Google simula la respuesta ya verificada por Authlib. No sustituye un inicio de sesión real con las credenciales del centro. La validación criptográfica OIDC corresponde a Authlib; no se ha reemplazado por una comprobación del correo enviada por el navegador.

Pendiente en la cuenta de destino: configurar Google OAuth, completar `backend/.env`, crear la base y administrador, subir la compilación, configurar WSGI y comprobar un inicio de sesión real y las restricciones de red del plan gratuito. Seguir el capítulo 3.

Actualización de invitaciones por correo: 23 pruebas de backend superadas y compilación Angular correcta. Se incluyen siete pruebas de invitaciones con SMTP simulado (contenido y destinatario individual, duplicados y reenvío, revocación, incertidumbre, permisos/configuración, TLS y errores de autenticación/cierre). Para comprobar la entrega real se requiere configurar la cuenta remitente y realizar un envío desde PythonAnywhere siguiendo el capítulo 7.
