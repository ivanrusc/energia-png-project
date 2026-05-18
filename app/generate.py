import os
import time
import shutil
import warnings
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.image as mpimg

from influxdb_client import InfluxDBClient
from influxdb_client.client.warnings import MissingPivotFunction


# Evita l'avís de pivot del client Python d'InfluxDB.
# No és un error. Nosaltres només necessitem _time i _value.
warnings.simplefilter("ignore", MissingPivotFunction)


def env(name, default=None, required=False):
    value = os.getenv(name, default)
    if required and (value is None or str(value).strip() == ""):
        raise ValueError(f"Falta la variable d'entorn requerida: {name}")
    return value


# ============================================================
# CONFIGURACIÓ DES DEL .env
# ============================================================

INFLUX_URL = env("INFLUX_URL", required=True)
INFLUX_TOKEN = env("INFLUX_TOKEN", required=True)
INFLUX_ORG = env("INFLUX_ORG", required=True)
INFLUX_BUCKET = env("INFLUX_BUCKET", required=True)

QUERY_MODE = env("QUERY_MODE", "matwifi_channel").strip().lower()

# Consum elèctric
POWER_MEASUREMENT = env("POWER_MEASUREMENT", "energy")
POWER_FIELD = env("POWER_FIELD", "power_w")
POWER_DEVICE = env("POWER_DEVICE", "em-Recoder")
POWER_CHANNEL = env("POWER_CHANNEL", "canal-0")

# Solar
SOLAR_MEASUREMENT = env("SOLAR_MEASUREMENT", "solar_production")
SOLAR_FIELD = env("SOLAR_FIELD", "power_w")

# Mode genèric field, només per compatibilitat
BASE_MEASUREMENT = env("BASE_MEASUREMENT", "")

# Temps
TIME_RANGE = env("TIME_RANGE", "-24h")
AGG_WINDOW = env("AGG_WINDOW", "1m")
REFRESH_SECONDS = int(env("REFRESH_SECONDS", "60"))
TIMEZONE = env("TIMEZONE", "Europe/Madrid")

# Publicació
PUBLIC_DOMAIN = env("PUBLIC_DOMAIN", "energia.matwifi.com")
PUBLIC_SLUG = env("PUBLIC_SLUG", "solar-consum-7fK29LmQp84XzR6v")
OUTPUT_BASE_DIR = env("OUTPUT_BASE_DIR", "/public")

# Fitxers
FILE_NAME_1 = env("FILE_NAME_1", "energia-1118x660.png")
WIDTH_1 = int(env("WIDTH_1", "1118"))
HEIGHT_1 = int(env("HEIGHT_1", "660"))

FILE_NAME_2 = env("FILE_NAME_2", "energia-900x531.png")
WIDTH_2 = int(env("WIDTH_2", "900"))
HEIGHT_2 = int(env("HEIGHT_2", "531"))

FILE_NAME_MAIN = env("FILE_NAME_MAIN", "energia.png")

# Estil
CHART_TITLE = env("CHART_TITLE", "Producció solar i consum elèctric")
CHART_SUBTITLE = env("CHART_SUBTITLE", "Últimes 24 hores · actualització cada 1 minut")
LOGO_PATH = env("LOGO_PATH", "/public/logo.png")

COLOR_BG = env("COLOR_BG", "#0b1220")
COLOR_PANEL = env("COLOR_PANEL", "#111827")
COLOR_GRID = env("COLOR_GRID", "#334155")
COLOR_TEXT = env("COLOR_TEXT", "#e5e7eb")
COLOR_MUTED = env("COLOR_MUTED", "#94a3b8")
COLOR_SOLAR = env("COLOR_SOLAR", "#ffcc00")
COLOR_CONSUMPTION = env("COLOR_CONSUMPTION", "#00ff88")


# ============================================================
# UTILITATS
# ============================================================

def fmt_power(value):
    if value is None or pd.isna(value):
        return "N/D"

    value = float(value)

    if abs(value) >= 1000:
        return f"{value / 1000:.2f} kW"

    return f"{value:.0f} W"


def latest_value(series: pd.Series):
    if series is None:
        return np.nan

    s = pd.to_numeric(series, errors="coerce").dropna()

    if s.empty:
        return np.nan

    return float(s.iloc[-1])


def latest_time_text(df: pd.DataFrame) -> str:
    if df is None or df.empty or "_time" not in df.columns:
        return "N/D"

    t = pd.to_datetime(df["_time"], utc=True, errors="coerce").dropna()

    if t.empty:
        return "N/D"

    return t.max().tz_convert(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y %H:%M")


def merge_query_frames(frames):
    if isinstance(frames, list):
        valid_frames = [
            f for f in frames
            if isinstance(f, pd.DataFrame) and not f.empty
        ]

        if not valid_frames:
            return pd.DataFrame()

        return pd.concat(valid_frames, ignore_index=True)

    if isinstance(frames, pd.DataFrame):
        return frames

    return pd.DataFrame()


def add_logo(fig):
    logo_file = Path(LOGO_PATH)

    if not logo_file.exists():
        return

    try:
        img = mpimg.imread(logo_file)
        ax_logo = fig.add_axes([0.84, 0.89, 0.11, 0.08], anchor="NE", zorder=50)
        ax_logo.imshow(img)
        ax_logo.axis("off")
    except Exception as e:
        print(f"[WARN] No s'ha pogut carregar el logo: {e}", flush=True)


def atomic_save_figure(fig, output_path: Path):
    tmp_path = output_path.with_suffix(".tmp.png")
    fig.savefig(tmp_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    tmp_path.replace(output_path)


def atomic_copy(src: Path, dst: Path):
    tmp = dst.with_suffix(".tmp.png")
    shutil.copyfile(src, tmp)
    tmp.replace(dst)


# ============================================================
# CONSULTES FLUX
# ============================================================

def build_matwifi_power_channel_query() -> str:
    return f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {TIME_RANGE})
  |> filter(fn: (r) => r["_measurement"] == "{POWER_MEASUREMENT}")
  |> filter(fn: (r) => r["_field"] == "{POWER_FIELD}")
  |> filter(fn: (r) => r["device"] == "{POWER_DEVICE}")
  |> filter(fn: (r) => r["channel"] == "{POWER_CHANNEL}")
  |> aggregateWindow(every: {AGG_WINDOW}, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value", "device", "channel"])
'''


def build_matwifi_solar_query() -> str:
    return f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {TIME_RANGE})
  |> filter(fn: (r) => r["_measurement"] == "{SOLAR_MEASUREMENT}")
  |> filter(fn: (r) => r["_field"] == "{SOLAR_FIELD}")
  |> aggregateWindow(every: {AGG_WINDOW}, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value"])
'''


def build_measurement_query(measurement_name: str) -> str:
    return f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {TIME_RANGE})
  |> filter(fn: (r) => r["_measurement"] == "{measurement_name}")
  |> aggregateWindow(every: {AGG_WINDOW}, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value"])
'''


def build_field_query(base_measurement: str, field_name: str) -> str:
    return f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {TIME_RANGE})
  |> filter(fn: (r) => r["_measurement"] == "{base_measurement}")
  |> filter(fn: (r) => r["_field"] == "{field_name}")
  |> aggregateWindow(every: {AGG_WINDOW}, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value"])
'''


def query_series(client: InfluxDBClient, query: str, series_name: str) -> pd.DataFrame:
    query_api = client.query_api()
    frames = query_api.query_data_frame(org=INFLUX_ORG, query=query)
    df = merge_query_frames(frames)

    if df.empty:
        return pd.DataFrame(columns=["_time", series_name])

    if "_time" not in df.columns or "_value" not in df.columns:
        print(f"[WARN] La consulta de {series_name} no retorna _time/_value.", flush=True)
        print(f"[WARN] Columnes rebudes: {list(df.columns)}", flush=True)
        return pd.DataFrame(columns=["_time", series_name])

    df = df[["_time", "_value"]].copy()
    df["_time"] = pd.to_datetime(df["_time"], utc=True, errors="coerce")
    df["_value"] = pd.to_numeric(df["_value"], errors="coerce")
    df = df.dropna(subset=["_time"])
    df = df.groupby("_time", as_index=False)["_value"].mean()
    df = df.rename(columns={"_value": series_name})
    df = df.sort_values("_time").reset_index(drop=True)

    return df


def get_data():
    with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as client:
        if QUERY_MODE == "matwifi_channel":
            q_power = build_matwifi_power_channel_query()
            q_solar = build_matwifi_solar_query()

        elif QUERY_MODE == "matwifi":
            q_power = build_matwifi_power_channel_query()
            q_solar = build_matwifi_solar_query()

        elif QUERY_MODE == "measurement":
            q_power = build_measurement_query(POWER_MEASUREMENT)
            q_solar = build_measurement_query(SOLAR_MEASUREMENT)

        elif QUERY_MODE == "field":
            if not BASE_MEASUREMENT:
                raise ValueError("QUERY_MODE=field però BASE_MEASUREMENT està buit.")

            q_power = build_field_query(BASE_MEASUREMENT, POWER_FIELD)
            q_solar = build_field_query(BASE_MEASUREMENT, SOLAR_FIELD)

        else:
            raise ValueError("QUERY_MODE incorrecte. Usa matwifi_channel, matwifi, measurement o field.")

        print("[DEBUG] Flux consum:", flush=True)
        print(q_power, flush=True)

        print("[DEBUG] Flux solar:", flush=True)
        print(q_solar, flush=True)

        df_power = query_series(client, q_power, "power_w")
        df_solar = query_series(client, q_solar, "solar_production")

    for df in [df_power, df_solar]:
        if not df.empty:
            df["_time"] = pd.to_datetime(df["_time"], utc=True, errors="coerce")
            df["time_local"] = df["_time"].dt.tz_convert(ZoneInfo(TIMEZONE))

    print(f"[DEBUG] Files consum: {len(df_power)}", flush=True)
    print(f"[DEBUG] Files solar: {len(df_solar)}", flush=True)

    if not df_power.empty:
        print("[DEBUG] Últimes files consum:", flush=True)
        print(df_power.tail(5).to_string(index=False), flush=True)

    if not df_solar.empty:
        print("[DEBUG] Últimes files solar:", flush=True)
        print(df_solar.tail(5).to_string(index=False), flush=True)

    return df_power, df_solar


# ============================================================
# RENDER IMATGES
# ============================================================

def render_empty_chart(output_path: Path, width_px: int, height_px: int, message: str):
    dpi = 100
    fig_w = width_px / dpi
    fig_h = height_px / dpi

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_facecolor(COLOR_BG)
    ax.set_facecolor(COLOR_PANEL)
    ax.axis("off")

    fig.text(0.06, 0.92, CHART_TITLE, color=COLOR_TEXT, fontsize=22, fontweight="bold")
    fig.text(0.06, 0.87, CHART_SUBTITLE, color=COLOR_MUTED, fontsize=11)
    fig.text(0.06, 0.45, message, color=COLOR_TEXT, fontsize=18)

    generated_at = datetime.now(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y %H:%M:%S")
    fig.text(
        0.06,
        0.08,
        f"Generat: {generated_at}",
        color=COLOR_MUTED,
        fontsize=10,
    )

    add_logo(fig)
    atomic_save_figure(fig, output_path)
    plt.close(fig)


def render_chart(df_power: pd.DataFrame, df_solar: pd.DataFrame, output_path: Path, width_px: int, height_px: int):
    if (df_power is None or df_power.empty) and (df_solar is None or df_solar.empty):
        render_empty_chart(output_path, width_px, height_px, "No hi ha dades disponibles.")
        return

    dpi = 100
    fig_w = width_px / dpi
    fig_h = height_px / dpi

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    fig.patch.set_facecolor(COLOR_BG)
    ax.set_facecolor(COLOR_PANEL)

    current_consum = np.nan
    current_solar = np.nan

    # -------------------------
    # Normalitza consum
    # -------------------------
    if df_power is None:
        df_power = pd.DataFrame(columns=["_time", "power_w", "time_local"])
    else:
        df_power = df_power.copy()

    if not df_power.empty:
        df_power["_time"] = pd.to_datetime(df_power["_time"], utc=True, errors="coerce")

        if "time_local" not in df_power.columns:
            df_power["time_local"] = df_power["_time"].dt.tz_convert(ZoneInfo(TIMEZONE))

        df_power["power_w"] = pd.to_numeric(df_power["power_w"], errors="coerce")
        df_power = df_power.dropna(subset=["time_local", "power_w"]).sort_values("_time")

    # -------------------------
    # Normalitza solar
    # -------------------------
    if df_solar is None:
        df_solar = pd.DataFrame(columns=["_time", "solar_production", "time_local"])
    else:
        df_solar = df_solar.copy()

    if not df_solar.empty:
        df_solar["_time"] = pd.to_datetime(df_solar["_time"], utc=True, errors="coerce")

        if "time_local" not in df_solar.columns:
            df_solar["time_local"] = df_solar["_time"].dt.tz_convert(ZoneInfo(TIMEZONE))

        df_solar["solar_production"] = pd.to_numeric(df_solar["solar_production"], errors="coerce")
        df_solar = df_solar.dropna(subset=["time_local", "solar_production"]).sort_values("_time")

    # -------------------------
    # Dibuixa consum primer
    # -------------------------
    if not df_power.empty:
        ax.plot(
            df_power["time_local"],
            df_power["power_w"],
            label=f"Consum {POWER_DEVICE} {POWER_CHANNEL}",
            linewidth=1.8,
            linestyle="-",
            color=COLOR_CONSUMPTION,
            marker=None,
            zorder=10,
        )
        current_consum = latest_value(df_power["power_w"])

    # -------------------------
    # Dibuixa solar després, a sobre
    # -------------------------
    if not df_solar.empty:
        ax.plot(
            df_solar["time_local"],
            df_solar["solar_production"],
            label="Producció solar",
            linewidth=1.8,
            linestyle="-",
            color=COLOR_SOLAR,
            marker=None,
            zorder=30,
        )

        ax.fill_between(
            df_solar["time_local"],
            df_solar["solar_production"].fillna(0),
            0,
            alpha=0.08,
            color=COLOR_SOLAR,
            zorder=5,
        )

        current_solar = latest_value(df_solar["solar_production"])

    # -------------------------
    # Escala Y amb les dues sèries
    # -------------------------
    all_values = []

    if not df_power.empty:
        all_values.extend(pd.to_numeric(df_power["power_w"], errors="coerce").dropna().tolist())

    if not df_solar.empty:
        all_values.extend(pd.to_numeric(df_solar["solar_production"], errors="coerce").dropna().tolist())

    if all_values:
        ymin = min(all_values)
        ymax = max(all_values)
        margin = max((ymax - ymin) * 0.15, 100)
        ax.set_ylim(max(0, ymin - margin), ymax + margin)

    # -------------------------
    # Estil eixos
    # -------------------------
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLOR_GRID)
    ax.spines["bottom"].set_color(COLOR_GRID)

    ax.tick_params(colors=COLOR_TEXT, labelsize=10)
    ax.grid(True, color=COLOR_GRID, alpha=0.35, linestyle="--", linewidth=0.7)

    ax.set_ylabel("Potència (W)", color=COLOR_TEXT, fontsize=11)
    ax.set_xlabel("Temps", color=COLOR_TEXT, fontsize=11)

    locator = mdates.AutoDateLocator(minticks=6, maxticks=10)
    formatter = mdates.DateFormatter("%d/%m %H:%M", tz=ZoneInfo(TIMEZONE))
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)

    for label in ax.get_xticklabels():
        label.set_rotation(25)
        label.set_horizontalalignment("right")

    # -------------------------
    # Textos superiors
    # -------------------------
    balance = current_solar - current_consum if not pd.isna(current_solar) and not pd.isna(current_consum) else np.nan

    solar_time = latest_time_text(df_solar)
    consum_time = latest_time_text(df_power)

    fig.text(0.06, 0.95, CHART_TITLE, color=COLOR_TEXT, fontsize=22, fontweight="bold")
    fig.text(0.06, 0.915, CHART_SUBTITLE, color=COLOR_MUTED, fontsize=11)

    stats = (
        f"Solar actual: {fmt_power(current_solar)} ({solar_time})   ·   "
        f"Consum actual: {fmt_power(current_consum)} ({consum_time})   ·   "
        f"Balanç: {fmt_power(balance)}"
    )
    fig.text(0.06, 0.885, stats, color=COLOR_TEXT, fontsize=11)

    debug_line = (
        f"Punts solar: {len(df_solar)}   ·   "
        f"Punts consum: {len(df_power)}"
    )
    fig.text(0.06, 0.86, debug_line, color=COLOR_MUTED, fontsize=10)

    generated_at = datetime.now(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y %H:%M:%S")
    fig.text(
        0.06,
        0.04,
        f"Última actualització: {generated_at} · Font: InfluxDB v2 ({PUBLIC_DOMAIN})",
        color=COLOR_MUTED,
        fontsize=10,
    )

    legend = ax.legend(
        loc="upper left",
        frameon=True,
        facecolor=COLOR_PANEL,
        edgecolor=COLOR_GRID,
        fontsize=10,
    )

    for txt in legend.get_texts():
        txt.set_color(COLOR_TEXT)

    add_logo(fig)

    fig.tight_layout(rect=[0.04, 0.08, 0.98, 0.82])
    atomic_save_figure(fig, output_path)
    plt.close(fig)


# ============================================================
# HTML
# ============================================================

def write_index(output_dir: Path):
    index_file = output_dir / "index.html"

    html = f"""<!doctype html>
<html lang="ca">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <title>Energia · MatWifi</title>
  <style>
    :root {{
      --bg:#0b1220;
      --panel:#111827;
      --text:#e5e7eb;
      --muted:#94a3b8;
      --accent:#38bdf8;
      --border:#334155;
    }}

    * {{
      box-sizing:border-box;
    }}

    body {{
      margin:0;
      background:var(--bg);
      color:var(--text);
      font-family:Arial, Helvetica, sans-serif;
    }}

    .wrap {{
      max-width:1200px;
      margin:0 auto;
      padding:24px;
    }}

    .card {{
      background:var(--panel);
      border:1px solid var(--border);
      border-radius:16px;
      padding:20px;
      margin-bottom:20px;
    }}

    h1 {{
      margin:0 0 8px 0;
    }}

    p {{
      color:var(--muted);
    }}

    img {{
      max-width:100%;
      height:auto;
      border-radius:12px;
      display:block;
    }}

    a {{
      color:var(--accent);
      text-decoration:none;
    }}

    ul {{
      padding-left:18px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Producció solar i consum elèctric</h1>
      <p>Gràfica actualitzada cada 1 minut.</p>
      <img id="chart" src="{FILE_NAME_MAIN}" alt="Gràfica energia">
    </div>

    <div class="card">
      <h2>Enllaços directes</h2>
      <ul>
        <li><a href="{FILE_NAME_MAIN}" target="_blank">{FILE_NAME_MAIN}</a></li>
        <li><a href="{FILE_NAME_1}" target="_blank">{FILE_NAME_1}</a></li>
        <li><a href="{FILE_NAME_2}" target="_blank">{FILE_NAME_2}</a></li>
      </ul>
    </div>
  </div>

  <script>
    function refreshChart() {{
      const img = document.getElementById('chart');
      img.src = '{FILE_NAME_MAIN}?t=' + Date.now();
    }}

    setInterval(refreshChart, {REFRESH_SECONDS * 1000});
  </script>
</body>
</html>
"""

    tmp_file = output_dir / "index.tmp.html"
    tmp_file.write_text(html, encoding="utf-8")
    tmp_file.replace(index_file)


# ============================================================
# GENERACIÓ
# ============================================================

def generate_once():
    output_dir = Path(OUTPUT_BASE_DIR) / PUBLIC_SLUG
    output_dir.mkdir(parents=True, exist_ok=True)

    df_power, df_solar = get_data()

    file_1 = output_dir / FILE_NAME_1
    file_2 = output_dir / FILE_NAME_2
    file_main = output_dir / FILE_NAME_MAIN

    render_chart(df_power, df_solar, file_1, 1600, 900)
    render_chart(df_power, df_solar, file_2, 1200, 675)

    atomic_copy(file_1, file_main)
    write_index(output_dir)

    print(f"[OK] Imatges generades a: {output_dir}", flush=True)


def main():
    print("[INFO] Iniciant generador PNG...", flush=True)
    print(f"[INFO] INFLUX_URL={INFLUX_URL}", flush=True)
    print(f"[INFO] INFLUX_BUCKET={INFLUX_BUCKET}", flush=True)
    print(f"[INFO] QUERY_MODE={QUERY_MODE}", flush=True)
    print(f"[INFO] POWER={POWER_MEASUREMENT}/{POWER_FIELD}/{POWER_DEVICE}/{POWER_CHANNEL}", flush=True)
    print(f"[INFO] SOLAR={SOLAR_MEASUREMENT}/{SOLAR_FIELD}", flush=True)
    print(f"[INFO] OUTPUT={Path(OUTPUT_BASE_DIR) / PUBLIC_SLUG}", flush=True)
    print(f"[INFO] REFRESH_SECONDS={REFRESH_SECONDS}", flush=True)

    while True:
        started_at = datetime.now(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y %H:%M:%S")
        print(f"[INFO] Nou cicle de generació: {started_at}", flush=True)

        try:
            generate_once()

        except Exception as e:
            print(f"[ERROR] Error generant les imatges: {e}", flush=True)

            output_dir = Path(OUTPUT_BASE_DIR) / PUBLIC_SLUG
            output_dir.mkdir(parents=True, exist_ok=True)

            render_empty_chart(output_dir / FILE_NAME_1, 1600, 900, f"Error: {e}")
            render_empty_chart(output_dir / FILE_NAME_2, 1200, 675, f"Error: {e}")
            atomic_copy(output_dir / FILE_NAME_1, output_dir / FILE_NAME_MAIN)

        print(f"[INFO] Esperant {REFRESH_SECONDS} segons...", flush=True)
        time.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    main()
