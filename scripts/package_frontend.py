"""Package the compiled frontend with the directory layout Flask expects."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
dist = root / 'frontend' / 'dist' / 'browser'
if not (dist / 'index.html').is_file():
    raise SystemExit('Ejecuta npm run build dentro de frontend antes de empaquetar.')
output = root / 'deploy'
output.mkdir(exist_ok=True)
archive = output / 'frontend-pythonanywhere.zip'
with ZipFile(archive, 'w', ZIP_DEFLATED) as bundle:
    for file in sorted(dist.rglob('*')):
        if file.is_file():
            bundle.write(file, file.relative_to(root))
print(archive)

application_archive = output / 'aplicacion-pythonanywhere.zip'
files = [f for f in dist.rglob('*') if f.is_file()]
files += [f for f in (root / 'backend' / 'app').rglob('*') if f.is_file() and f.suffix in ('.py', '.json', '.sql')]
files += [root / 'backend' / name for name in ('requirements.txt', 'wsgi.py', '.env.example')]
files += list((root / 'manual').glob('*.md'))
with ZipFile(application_archive, 'w', ZIP_DEFLATED) as bundle:
    for file in sorted(files):
        bundle.write(file, file.relative_to(root))
print(application_archive)
