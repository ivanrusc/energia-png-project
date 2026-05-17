# Energia PNG Project

Projecte Docker per generar una imatge PNG de producció solar + consum elèctric des d’InfluxDB v2.

Llegeix el manual principal:

```text
MANUAL-pas-a-pas.md
```

## Instal·lació ràpida

```bash
cp .env.example .env
nano .env
sudo docker compose up -d
sudo docker compose logs -f energia-png-generator
```

## URL esperada

```text
https://energia.EL-MEU-DOMINI.com/solar-consum-/energia.png
```
