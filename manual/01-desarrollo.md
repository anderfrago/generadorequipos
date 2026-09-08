# Desarrollo y compilación

## Requisitos

- Python 3.10 o superior, con `venv` y SQLite.
- Node.js 22.22.3+, 24.15.0+ o 26.x, en las ramas admitidas por Angular 22.
- npm. No se necesita instalar Angular CLI globalmente.

Compatibilidad oficial: https://angular.dev/reference/versions (Angular 22 requiere TypeScript 6.0; el proyecto lo declara).

## Backend (PowerShell, raíz del proyecto)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
Copy-Item backend/.env.example backend/.env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copiar la clave generada en `SECRET_KEY` de `backend/.env`. Completar Google OAuth siguiendo el siguiente capítulo. Indicar `ADMIN_EMAIL` con la cuenta corporativa inicial. Para desarrollo: `PUBLIC_BASE_URL=http://localhost:5000` y `COOKIE_SECURE=false`.

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m flask --app app:create_app init-db
..\.venv\Scripts\python.exe -m flask --app app:create_app run --port 5000
```

## Frontend

En otra terminal desde la raíz:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run build
```

Abrir `http://localhost:5000`: Flask sirve Angular compilado y la API desde el mismo origen. Volver a compilar para ver cambios.

Para edición continua se puede ejecutar `npm.cmd start` en el puerto 4200 con el proxy incluido. Para probar OAuth y enlaces individuales utilizar el puerto 5000, que coincide con la URL pública configurada. El callback OAuth está registrado en el puerto 5000.

El resultado que se sube al servidor es `frontend/dist/browser/`. No subir `node_modules`, `.venv`, bases de datos de pruebas ni credenciales locales.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

