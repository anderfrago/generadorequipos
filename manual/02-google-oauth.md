# Acceso con Google

## Crear las credenciales

1. Entrar en Google Cloud Console con una cuenta autorizada y crear o seleccionar un proyecto.
2. En Google Auth Platform, configurar la pantalla de consentimiento: nombre, correo de soporte y audiencia. Elegir audiencia interna si el proyecto pertenece a la organización Workspace y está disponible.
3. Solicitar únicamente `openid`, `email` y `profile`. Ya no se requieren permisos de Sheets, Drive, Docs ni envío de correo.
4. Crear un cliente OAuth de tipo **Aplicación web**.
5. Añadir estas URI de redirección autorizadas, con coincidencia exacta:
   - Desarrollo: `http://localhost:5000/auth/callback`
   - Producción EE. UU.: `https://USUARIO.pythonanywhere.com/auth/callback`
   - Producción UE, si tu cuenta está allí: `https://USUARIO.eu.pythonanywhere.com/auth/callback`
6. Guardar el identificador y secreto del cliente en `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET` dentro de `backend/.env`.

No poner el secreto en Angular. Este flujo usa redirecciones gestionadas por Flask; no requiere un botón JavaScript de Google ni orígenes JavaScript autorizados. Si Google mantiene la aplicación en pruebas con audiencia externa, añadir los usuarios de prueba permitidos en la consola.

## Autorización docente

El acceso exige un token de Google verificado, correo confirmado, dominio Workspace `cuatrovientos.org` y una cuenta activa en la tabla `users`. El parámetro visual `hd` del formulario Google no se utiliza como única comprobación de seguridad.

El administrador inicial se crea mediante `ADMIN_EMAIL` al ejecutar `flask --app app:create_app init-db`. Para autorizar otra cuenta desde la consola del servidor, con el entorno virtual activado y dentro de `backend`:

```bash
flask --app app:create_app add-teacher docente@cuatrovientos.org --name "Nombre del docente"
```

Añadir `--admin` solo para conceder acceso administrativo a todas las clases. Los docentes ordinarios acceden a las clases que crean o a las que se les asigna.

## Comprobación real en PythonAnywhere

Las cuentas gratuitas restringen conexiones salientes mediante una lista permitida. El flujo necesita acceso a la metadata de `accounts.google.com`, al endpoint de tokens y a los certificados de `googleapis.com`. Revisar la lista vigente y probar un inicio de sesión real una vez desplegado; una prueba local no verifica las restricciones de la cuenta.

- https://www.pythonanywhere.com/whitelist/
- https://help.pythonanywhere.com/pages/403ForbiddenError/
- https://developers.google.com/identity/openid-connect/openid-connect

Si aparece `redirect_uri_mismatch`, comprobar esquema HTTPS, región, usuario y `/auth/callback`. Si Google autentica pero la aplicación devuelve 403, verificar dominio y alta docente. No desactivar la validación de identidad para resolver errores de configuración.

