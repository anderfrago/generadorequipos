# Despliegue en PythonAnywhere gratuito

## 1. Preparar y subir

Compilar Angular localmente según el capítulo 1. Crear una cuenta en la región elegida de PythonAnywhere. La cuenta gratuita utiliza su subdominio asignado.

Subir a `/home/USUARIO/formacion-equipos/`:

```text
backend/
  app/
  requirements.txt
  wsgi.py
  .env.example
frontend/
  dist/
    browser/
      index.html
      main-....js
      styles-....css
manual/
```

Puede usarse el apartado Files para subir un ZIP y extraerlo desde una consola Bash. Comprobar que no se ha creado un nivel adicional de carpetas. No hace falta Node.js en el alojamiento para servir el resultado compilado.

## 2. Entorno Python

Abrir una consola Bash. Elegir una versión Python disponible en tu cuenta, igual en el entorno virtual y en la web; este ejemplo usa 3.10:

```bash
cd /home/USUARIO/formacion-equipos
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Editar `backend/.env` mediante Files. Configurar:

```dotenv
SECRET_KEY=CLAVE_ALEATORIA_GENERADA
GOOGLE_CLIENT_ID=CLIENTE_REAL
GOOGLE_CLIENT_SECRET=SECRETO_REAL
TEACHER_DOMAIN=cuatrovientos.org
ADMIN_EMAIL=administrador@cuatrovientos.org
PUBLIC_BASE_URL=https://USUARIO.pythonanywhere.com
COOKIE_SECURE=true
DATABASE_PATH=/home/USUARIO/formacion-equipos/instance/app.sqlite3
```

Para cuentas de la UE cambiar `PUBLIC_BASE_URL` a `https://USUARIO.eu.pythonanywhere.com`. No dejar los valores de ejemplo.

```bash
chmod 600 backend/.env
cd backend
flask --app app:create_app init-db
```

La base se crea en `instance`, fuera de las carpetas públicas. La inicialización no borra tablas existentes. No ejecutar Flask con `--debug` en producción.

## 3. Crear la web WSGI

En **Web → Add a new web app**, seleccionar el subdominio gratuito, **Manual configuration** y la versión Python elegida.

- Source code: `/home/USUARIO/formacion-equipos/backend`
- Working directory: `/home/USUARIO/formacion-equipos/backend`
- Virtualenv: `/home/USUARIO/formacion-equipos/.venv`

Editar el archivo WSGI enlazado en el panel Web y reemplazar su contenido por:

```python
import sys

backend_path = '/home/USUARIO/formacion-equipos/backend'
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app import create_app
application = create_app()
```

No llamar a `app.run()`. Flask sirve los archivos compilados de Angular y devuelve `index.html` para rutas como `/teacher` y `/student`. No crear una asignación estática `/` que intercepte `/api` y `/auth`. Para este tamaño de aplicación no se requieren asignaciones estáticas adicionales.

Activar **Force HTTPS** en el panel cuando esté disponible y pulsar **Reload**.

## 4. Verificar

1. Abrir `https://TU_SUBDOMINIO/api/health` y comprobar `{"status":"ok"}`.
2. Abrir la página principal y entrar con Google como administrador.
3. Crear una clase y un alumno de prueba.
4. Generar su enlace y abrirlo en una ventana privada.
5. Completar, guardar y enviar un cuestionario.
6. Con al menos tres respuestas completas, generar y validar equipos.
7. Descargar informes y comprobar su contenido.
8. Recargar la web y verificar que los datos siguen disponibles.

## Límites y diagnóstico

### Error «Compila Angular siguiendo manual/01-desarrollo.md.»

La API Flask funciona, pero no encuentra `index.html`. La carpeta compilada está excluida de Git: subir solo el repositorio no la incluye.

En tu ordenador, ejecutar `npm run build` dentro de `frontend` y después, desde la raíz, `python scripts/package_frontend.py`. Subir `deploy/frontend-pythonanywhere.zip` a PythonAnywhere y extraerlo desde la raíz del proyecto:

```bash
cd /home/USUARIO/formacion-equipos
unzip -o /home/USUARIO/frontend-pythonanywhere.zip
source .venv/bin/activate
cd backend
flask --app app:create_app check-frontend
```

Adaptar la ubicación del ZIP a la carpeta donde se ha subido. El archivo incluye la estructura `frontend/dist/browser/`. No extraerlo dentro de `backend` ni dentro de `frontend`, porque duplicaría niveles.

Con el backend actualizado, se puede indicar una ruta distinta mediante `FRONTEND_DIST=/ruta/absoluta/a/la/carpeta/que/contiene/index.html` en `backend/.env`. Pulsar **Reload** en Web después de actualizar código o configuración.

Consultar las condiciones de la cuenta gratuita y renovar la web desde el panel antes de la fecha de caducidad que muestre. Vigilar almacenamiento y CPU. SQLite se ha elegido para este despliegue pequeño; las operaciones de escritura se serializan.

- **502/500:** revisar el error log enlazado desde Web; comprobar dependencias, secreto y versión Python.
- **503 al abrir la interfaz:** falta `frontend/dist/browser/index.html`.
- **No such table:** ejecutar `init-db` con el mismo `.env` que utiliza la web.
- **Unable to open database file:** comprobar ruta absoluta y permisos de `instance`.
- **403 en OAuth:** consultar el capítulo 2 y la lista permitida de conexiones salientes.
- **Bucle de sesión:** usar HTTPS y comprobar `PUBLIC_BASE_URL` y `COOKIE_SECURE`.

Referencias oficiales:

- https://help.pythonanywhere.com/pages/Flask/
- https://help.pythonanywhere.com/pages/FreeAccountsFeatures/
- https://help.pythonanywhere.com/pages/UsingANewDomainForExistingWebApp/
