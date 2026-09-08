# Envío de invitaciones con Google Workspace

La aplicación puede enviar un correo separado a cada alumno con el nombre del curso, curso académico, evaluación, instrucciones y su enlace individual. Utiliza una cuenta remitente de Google Workspace configurada en el servidor. El campo Reply-To se dirige al docente que inicia el envío.

## 1. Preparar la cuenta remitente

Elegir una cuenta de Cuatrovientos autorizada para este uso. Activar verificación en dos pasos y crear una contraseña de aplicación para «Equipos equilibrados», si la política del centro lo permite. No usar la contraseña habitual ni el secreto del cliente OAuth.

La posibilidad de crear contraseñas de aplicación depende de la cuenta y de las políticas de Google Workspace. Si la opción no está disponible, consultar con la administración de Workspace del centro; esta implementación SMTP necesita esa credencial. No basta con haber configurado el inicio de sesión con Google: son configuraciones independientes.

- [Contraseñas de aplicación de Google](https://support.google.com/accounts/answer/185833?hl=es).
- [Enviar correo desde una aplicación con Workspace](https://support.google.com/a/answer/176600).

## 2. Actualizar el servidor

Subir el nuevo `deploy/aplicacion-pythonanywhere.zip` y extraerlo en la raíz real del proyecto, que en tu cuenta es `/home/formadorequipos/formadorequipos`. El ZIP contiene backend, frontend compilado y manual, sin `.env` ni SQLite.

Con el entorno virtual del sitio activado:

```bash
cd /home/formadorequipos/formadorequipos/backend
python -m pip install -r requirements.txt
python -m flask --app app:create_app upgrade-db
```

`upgrade-db` crea la tabla de registro de invitaciones e índices que faltan. No borra datos ni modifica roles o usuarios existentes. Si el comando no aparece, comprobar que se ha subido el backend nuevo, no solo la compilación Angular.

## 3. Configurar backend/.env

Añadir:

```dotenv
MAIL_HOST=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=cuenta.remitente@cuatrovientos.org
MAIL_PASSWORD=CONTRASENA_DE_APLICACION
MAIL_FROM=cuenta.remitente@cuatrovientos.org
MAIL_FROM_NAME=Cuatrovientos · Equipos equilibrados
PUBLIC_BASE_URL=https://formadorequipos.pythonanywhere.com
```

Sustituir cuenta y contraseña por los valores reales. Pegar la contraseña de aplicación sin espacios de presentación. `MAIL_FROM` debe ser la cuenta autenticada o un alias autorizado en Google; si queda vacío, se usa `MAIL_USERNAME`. La conexión utiliza STARTTLS con verificación del certificado. No se admite envío sin cifrado.

Conservar el resto de variables de `.env` y los permisos privados del archivo. No poner credenciales en Angular, Git ni mensajes de chat. Pulsar **Reload** en Web.

## 4. Enviar desde la aplicación

1. Entrar como docente autorizado y abrir la clase.
2. Comprobar nombres y correos del alumnado. Generar los enlaces mediante **Preparar enlaces** o el botón individual **Enlace**.
3. Abrir **Invitaciones por correo**.
4. Revisar remitente, dirección de respuesta, vista previa y estado de cada alumno.
5. Pulsar **Enviar invitación** para una persona o **Enviar invitaciones pendientes** para las elegibles.
6. Mantener la página abierta mientras avanza el envío. Cada petición envía un solo correo, evitando un proceso largo de servidor para toda la clase.

Un enlace revocado no se reactiva por enviar correo: se debe emitir de nuevo previamente. Las personas sin correo válido y los cuestionarios ya enviados quedan excluidos. Cada correo contiene exclusivamente el enlace de su destinatario; no hay listas de destinatarios compartidas.

## Estados y reenvíos

- **Pendiente:** no hay envíos registrados.
- **Enlace actualizado:** la dirección o el enlace ya no coinciden con el último envío.
- **En curso:** otro envío está procesándose.
- **Aceptado por el servidor:** Google aceptó el mensaje; no acredita entrega ni lectura. Revisar posibles devoluciones en la cuenta remitente.
- **Fallido:** hubo un rechazo confirmado o no se pudo iniciar el envío. Resolver la causa y volver a enviar.
- **Sin confirmación:** una desconexión o interrupción impidió confirmar el resultado. Se excluye del envío automático de pendientes. Revisar el buzón o el correo enviado antes de usar **Reenviar**.

El botón **Reenviar** pide una confirmación explícita. Un envío en curso que lleve más de dos minutos sin actualizarse se muestra como sin confirmación. Las peticiones repetidas con el mismo identificador no vuelven a enviar el correo. El lote se detiene ante un error para permitir revisar su causa; los mensajes ya aceptados se conservan en el registro y se excluyen al continuar con pendientes.

## PythonAnywhere gratuito y diagnóstico

PythonAnywhere documenta una excepción para Gmail SMTP en cuentas gratuitas. Puede haber bloqueos temporales si cambian las direcciones de los servidores de Google; hay que comprobarlo en la cuenta real. Otros servidores SMTP no tienen necesariamente esa excepción. [Documentación de PythonAnywhere](https://helpdev.pythonanywhere.com/pages/SMTPForFreeUsers).

- **Credenciales rechazadas:** comprobar contraseña de aplicación, cuenta completa y autorización del centro. Si se cambia la contraseña de Google puede ser necesario generar una contraseña de aplicación nueva.
- **Conexión fallida:** comprobar host, puerto 587 y conectividad del plan gratuito. No cambiar a una conexión sin TLS.
- **Mensaje rechazado:** revisar destinatario, remitente/alias y cuota disponible de Google Workspace.
- **Falta la tabla invitation_deliveries:** ejecutar `upgrade-db` con el mismo entorno y base que utiliza WSGI.
- **Enlace incorrecto:** revisar `PUBLIC_BASE_URL` y recargar la web antes de reenviar.

## Verificación realizada

Las pruebas automatizadas simulan el transporte SMTP: contenido individual, exclusión de enlaces ajenos, autenticación y TLS, prevención de duplicados, reenvío explícito, enlaces revocados, permisos y resultados inciertos. No se han enviado correos reales durante el desarrollo. Tras configurar la cuenta, realizar un primer envío a un alumno de prueba con un buzón bajo tu control y comprobar el enlace recibido.
