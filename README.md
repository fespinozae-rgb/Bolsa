# Monitor Bursátil — Chile (100% automático)

Dashboard estático que se actualiza solo, todos los días de mercado a las
~17:00 hora de Chile, usando GitHub Actions + Yahoo Finance (`yfinance`).
No requiere servidor propio ni plan pago: todo corre gratis en GitHub.

## Cómo funciona

```
GitHub Actions (cron diario 17:00 CLT)
        │
        ▼
scripts/fetch_data.py  ──►  yfinance (Yahoo Finance, tickers .SN)
        │
        ▼
data/history.json  (se hace commit automático cada día)
        │
        ▼
index.html  (GitHub Pages lo sirve y lo lee con fetch())
```

## Configuración (una sola vez, ~10 minutos)

1. **Crea un repositorio en GitHub.**
   Ve a https://github.com/new, ponle un nombre (ej. `monitor-bursatil-chile`),
   márcalo como público (necesario para GitHub Pages gratis) y créalo.

2. **Sube estos archivos al repositorio**, respetando la estructura de carpetas:
   ```
   .github/workflows/update-data.yml
   scripts/fetch_data.py
   data/history.json
   index.html
   README.md
   ```
   Puedes arrastrarlos directamente en la interfaz web de GitHub ("Add file" →
   "Upload files"), o clonar el repo vacío y hacer `git add . && git commit && git push`.

3. **Dale permiso de escritura a las Actions** (para que puedan hacer commit
   de los datos nuevos cada día):
   Settings → Actions → General → baja hasta "Workflow permissions" →
   selecciona **"Read and write permissions"** → Save.

4. **Activa GitHub Pages:**
   Settings → Pages → en "Source" elige **"Deploy from a branch"** →
   branch `main`, carpeta `/ (root)` → Save.
   GitHub te dará una URL como `https://tu-usuario.github.io/monitor-bursatil-chile/`.

5. **Corre la tarea una vez manualmente** para confirmar que todo funciona:
   pestaña "Actions" → "Actualizar datos Bolsa de Santiago" → "Run workflow".
   Revisa los logs; si algún ticker falla, lo verás marcado como `[skip]` o
   `[error]` pero el resto seguirá funcionando.

6. Listo. Desde ahora, cada día hábil a las 17:00 (hora de Chile) el archivo
   `data/history.json` se actualiza solo y el sitio muestra los datos nuevos
   sin que tengas que hacer nada.

## Personalizar

- **Agregar o quitar acciones:** edita el diccionario `TICKERS` en
  `scripts/fetch_data.py`. El símbolo local es la clave; el ticker de Yahoo
  Finance (sufijo `.SN` para Santiago) es el valor. Puedes buscar tickers en
  https://finance.yahoo.com/lookup — no todas las acciones chilenas
  (especialmente las muy poco líquidas) tienen datos ahí.
- **Cambiar el horario:** edita la línea `cron` en
  `.github/workflows/update-data.yml`. GitHub Actions usa hora UTC; Chile es
  UTC-4 (CLT) u UTC-3 en horario de verano (CLST).
- **Sectores:** el diccionario `SECTORS` en `fetch_data.py` define a qué
  sector pertenece cada símbolo, para calcular el rendimiento promedio por
  sector. Ajusta las categorías como prefieras.

## Limitaciones a tener en cuenta

- Yahoo Finance no cubre todas las acciones chilenas — el universo inicial
  cubre ~28 de las más líquidas / grandes. Amplíalo según tus intereses.
- El histórico crece indefinidamente en un solo archivo JSON; si en un año
  tienes cientos de capturas y el archivo pesa mucho, puedes migrar a un
  archivo por mes o a una base de datos liviana (ej. SQLite) sin cambiar la
  lógica general.
- Esta información es referencial, puede contener errores o desfases frente
  a la fuente oficial (Bolsa de Santiago / CMF), y no constituye asesoría
  de inversión.
