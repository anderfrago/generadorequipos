# Actualizaciones y copias de seguridad

## Copia consistente de SQLite

Desde la raíz del proyecto en una consola Bash de PythonAnywhere, con el entorno virtual activado:

```bash
mkdir -p backups
python -c "import sqlite3,datetime; source=sqlite3.connect('instance/app.sqlite3'); target=sqlite3.connect('backups/equipos-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3'); source.backup(target); target.close(); source.close()"
```

Si has cambiado `DATABASE_PATH`, adaptar la ruta origen. La API `backup` obtiene una copia consistente incluso con la aplicación activa. Descargar periódicamente las copias a un lugar privado; no dejarlas dentro de `frontend/dist`. Guardar también `.env` en un almacén seguro separado.

## Actualizar

1. Crear una copia y conservar la versión anterior del código y del frontend compilado.
2. Ejecutar las pruebas y compilar Angular localmente con `npm ci` y `npm run build`.
3. Subir el nuevo backend y el contenido completo de `frontend/dist/browser`.
4. Con el entorno virtual del servidor activo, ejecutar `pip install -r backend/requirements.txt`.
5. Aplicar únicamente las migraciones de esquema indicadas por la nueva versión. `init-db` crea tablas ausentes pero no transforma columnas existentes.
6. Pulsar Reload y repetir las comprobaciones esenciales.

Conservar `instance/app.sqlite3` y `backend/.env`. No reemplazarlos por archivos de desarrollo. Para evitar mezclas de archivos durante una actualización, subir el nuevo frontend a una carpeta temporal y sustituir la carpeta publicada durante una ventana de mantenimiento.

## Restaurar

Desactivar temporalmente la web desde Web para impedir escrituras. Conservar una copia de la base que se va a sustituir. Restaurar la copia elegida en la ruta `DATABASE_PATH`, con los mismos permisos del usuario. Restaurar una versión del código compatible con esa base, reactivar y recargar la web. Probar el acceso y una consulta antes de retomar el uso normal.

No restaurar copiando encima de una base que está recibiendo escrituras. Las copias contienen nombres, respuestas y observaciones: solo deben estar disponibles para las personas autorizadas.
