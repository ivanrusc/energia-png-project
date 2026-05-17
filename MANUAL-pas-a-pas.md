# Manual pas a pas — Publicar gràfica PNG d’InfluxDB v2 a Internet

Aquest projecte genera una imatge PNG cada minut amb dues línies:

- Producció solar
- Consum elèctric

La imatge es genera des d’InfluxDB v2 amb Flux, es desa en una carpeta pública i es publica amb Nginx darrere de Nginx Proxy Manager.

## 1. Arquitectura

```text
InfluxDB v2 privat
  ↓ Flux query amb token només lectura
Docker: energia-png-generator
  ↓ genera PNG cada 60 segons
/srv/docker/energia-png/public/<slug>/energia.png
  ↓
Docker: energia-png-web, Nginx estàtic sense cache
  ↓
Nginx Proxy Manager + SSL
  ↓
https://energia.EL-MEU-DOMIN.com/solar-consum-/energia.png
```

## 2. Fitxers del projecte

```text
energia-png/
├── compose.yaml
├── .env.example
├── MANUAL-pas-a-pas.md
├── app/
│   ├── generate.py
│   └── requirements.txt
├── nginx/
│   └── default.conf
├── public/
│   └── .gitkeep
└── scripts/
    ├── restart.sh
    ├── check-files.sh
    └── check-cache.sh
```

## 3. Crear la carpeta al servidor

```bash
sudo mkdir -p /srv/docker/energia-png
sudo chown -R "$USER:$USER" /srv/docker/energia-png
cd /srv/docker/energia-png
```

Copia aquí tots els fitxers del ZIP.

## 4. Crear el fitxer `.env`

```bash
cp .env.example .env
nano .env
```

Canvia com a mínim:

```env
INFLUX_TOKEN=POSA_AQUI_EL_TOKEN_DE_LECTURA
```

Configuració validada per aquest projecte:

```env
INFLUX_URL=http://IP-SERVIDOR:8086
INFLUX_ORG=NOM-DEL-PROJECTE
INFLUX_BUCKET=NOM-DEL-BUCKET

QUERY_MODE=EL-MEU-DOMIN_channel

POWER_MEASUREMENT=energy
POWER_FIELD=power_w
POWER_DEVICE=em-Recoder
POWER_CHANNEL=canal-0

SOLAR_MEASUREMENT=solar_production
SOLAR_FIELD=power_w

TIME_RANGE=-24h
AGG_WINDOW=1m
REFRESH_SECONDS=60
TIMEZONE=Europe/Madrid

PUBLIC_DOMAIN=energia.EL-MEU-DOMIN.com
PUBLIC_SLUG=solar-consum-
```

## 5. Crear token de només lectura a InfluxDB v2

A InfluxDB v2:

```text
Load Data / Data → API Tokens → Generate API Token → Custom API Token
```

Permisos recomanats:

```text
Read bucket: NOM-DEL-BUCKET
```

No donis permisos d’escriptura ni permisos d’administració si només és per generar la gràfica.

## 6. Arrencar el projecte

```bash
cd /srv/docker/energia-png
sudo docker compose up -d
```

Veure logs:

```bash
sudo docker compose logs -f energia-png-generator
```

Has de veure alguna cosa semblant a:

```text
[INFO] Iniciant generador PNG...
[INFO] QUERY_MODE=EL-MEU-DOMIN_channel
[INFO] POWER=energy/power_w/em-Recoder/canal-0
[INFO] SOLAR=solar_production/power_w
[DEBUG] Files consum: 1441
[DEBUG] Files solar: 288
[OK] Imatges generades a: /public/solar-consum-
[INFO] Esperant 60 segons...
```

## 7. Provar localment

```bash
curl -I http://127.0.0.1:8090/solar-consum-/energia.png
```

També pots descarregar la imatge:

```bash
curl -s http://127.0.0.1:8090/solar-consum-/energia.png -o /tmp/energia.png
ls -lh /tmp/energia.png
```

URL local al navegador:

```text
http://IP_DEL_SERVIDOR:8090/solar-consum-/
```

Imatge directa:

```text
http://IP_DEL_SERVIDOR:8090/solar-consum-/energia.png
```

## 8. Publicar amb Nginx Proxy Manager

A Nginx Proxy Manager:

```text
Proxy Hosts → Add Proxy Host
```

### Details

```text
Domain Names: energia.EL-MEU-DOMIN.com
Scheme: http
Forward Hostname / IP: IP_DEL_SERVIDOR
Forward Port: 8090
Cache Assets: OFF
Block Common Exploits: ON
Websockets Support: OFF
```

### SSL

```text
Request a new SSL Certificate: ON
Force SSL: ON
HTTP/2 Support: ON
```

### Access

```text
Publicly Accessible
```

### Advanced

Afegeix:

```nginx
proxy_no_cache 1;
proxy_cache_bypass 1;

add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0" always;
add_header Pragma "no-cache" always;
add_header Expires "0" always;
```

## 9. URLs finals

Pàgina:

```text
https://energia.EL-MEU-DOMIN.com/solar-consum-/
```

Imatge principal:

```text
https://energia.EL-MEU-DOMIN.com/solar-consum-/energia.png
```

Imatges de mida fixa:

```text
https://energia.EL-MEU-DOMIN.com/solar-consum-/energia-1600x900.png
https://energia.EL-MEU-DOMIN.com/solar-consum-/energia-1200x675.png
```

## 10. Comprovar que la imatge es regenera

```bash
cd /srv/docker/energia-png
watch -n 10 'date; stat -c "%y  %s  %n" public/solar-consum-/energia*.png'
```

Si la data canvia cada minut, el generador funciona.

També pots fer servir l’script inclòs:

```bash
./scripts/check-files.sh
```

## 11. Comprovar cache HTTP

```bash
curl -I https://energia.EL-MEU-DOMIN.com/solar-consum-/energia.png
```

Ha de sortir alguna cosa semblant a:

```text
Cache-Control: no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0
Pragma: no-cache
Expires: 0
```

No hauria de sortir:

```text
Cache-Control: max-age=29647
Expires: ...
```

També pots fer servir:

```bash
./scripts/check-cache.sh
```

## 12. Reiniciar el projecte

```bash
cd /srv/docker/energia-png
sudo docker compose down
sudo docker compose up -d --force-recreate
sudo docker compose logs -f energia-png-generator
```

O amb l’script:

```bash
./scripts/restart.sh
```

## 13. Comandes útils

### Estat dels contenidors

```bash
sudo docker compose ps
```

### Logs del generador

```bash
sudo docker compose logs -f energia-png-generator
```

### Logs del Nginx intern

```bash
sudo docker compose logs -f energia-png-web
```

### Veure només resum de dades

```bash
sudo docker compose logs --tail=120 energia-png-generator | grep -E "Files consum|Files solar|Últimes files consum|Últimes files solar"
```

### Reiniciar només el web intern

```bash
sudo docker compose restart energia-png-web
```

### Reiniciar només el generador

```bash
sudo docker compose restart energia-png-generator
```

### Verificar fitxers generats

```bash
ls -lh public/solar-consum-/
stat public/solar-consum-/energia.png
```

### Comparar fitxer local amb el servit pel Nginx intern

```bash
sha256sum public/solar-consum-/energia.png
curl -s http://127.0.0.1:8090/solar-consum-/energia.png -o /tmp/energia_8090.png
sha256sum /tmp/energia_8090.png
```

### Comparar amb la URL pública

```bash
curl -s https://energia.EL-MEU-DOMIN.com/solar-consum-/energia.png -o /tmp/energia_publica.png
sha256sum public/solar-consum-/energia.png /tmp/energia_publica.png
```

## 14. Diagnòstic de problemes

### Problema: no surt el consum

Mira els logs:

```bash
sudo docker compose logs --tail=120 energia-png-generator | grep "Files consum"
```

Si surt:

```text
Files consum: 0
```

revisa al `.env`:

```env
POWER_MEASUREMENT=energy
POWER_FIELD=power_w
POWER_DEVICE=em-Recoder
POWER_CHANNEL=canal-0
```

Consulta Flux per provar a Grafana/InfluxDB:

```flux
from(bucket: "NOM-DEL-BUCKET")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "energy")
  |> filter(fn: (r) => r["_field"] == "power_w")
  |> filter(fn: (r) => r["device"] == "em-Recoder")
  |> filter(fn: (r) => r["channel"] == "canal-0")
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value", "device", "channel"])
```

### Problema: no surt la solar

Mira:

```bash
sudo docker compose logs --tail=120 energia-png-generator | grep "Files solar"
```

Consulta Flux:

```flux
from(bucket: "NOM-DEL-BUCKET")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "solar_production")
  |> filter(fn: (r) => r["_field"] == "power_w")
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value"])
```

### Problema: la imatge no s’actualitza a Internet

Comprova primer que el fitxer local canvia:

```bash
watch -n 10 'date; stat -c "%y  %s  %n" public/solar-consum-/energia*.png'
```

Si el fitxer local canvia, però la URL pública no, és cache. Revisa:

- `Cache Assets` desactivat a Nginx Proxy Manager
- headers `Cache-Control` a Advanced
- si uses Cloudflare, posa el subdomini en `DNS only` o crea una regla `Cache Bypass`

## 15. Personalització visual

### Fer les línies més fines

Al `generate.py`, busca `linewidth=1.8` i canvia-ho per:

```python
linewidth=1.2
```

### Canviar colors

Al `.env`:

```env
COLOR_SOLAR=#ffcc00
COLOR_CONSUMPTION=#00ff88
```

### Afegir logo

Copia el logo aquí:

```bash
cp logo.png /srv/docker/energia-png/public/logo.png
```

El `.env` ja apunta a:

```env
LOGO_PATH=/public/logo.png
```

## 16. Backup ràpid del projecte

```bash
cd /srv/docker
sudo tar -czf "$(date +%F_%H-%M)_energia-png.tar.gz" energia-png
```

## 17. Actualitzar el codi

Abans de tocar `generate.py`:

```bash
cd /srv/docker/energia-png
cp app/generate.py app/generate.py.bak-$(date +%F_%H-%M)
```

Editar:

```bash
nano app/generate.py
```

Reiniciar:

```bash
sudo docker compose down
sudo docker compose up -d --force-recreate
sudo docker compose logs -f energia-png-generator
```

## 18. Notes de seguretat

Aquest projecte publica una URL difícil, no una autenticació forta.

Recomanacions:

- No posis tokens a `public/`.
- No publiquis `.env`.
- El token d’InfluxDB ha de ser només de lectura.
- Mantén `PUBLIC_SLUG` llarg i difícil.
- Mantén `X-Robots-Tag: noindex`.
- No activis llistat de directoris.

