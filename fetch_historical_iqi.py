"""
fetch_historical_iqi.py
-----------------------
Descarga datos históricos de Cloudflare Radar IQI para todos los países
de América, mes a mes, y exporta a CSV.

Uso:
    python fetch_historical_iqi.py
    python fetch_historical_iqi.py --start 2024-01-01 --end 2025-06-01
    python fetch_historical_iqi.py --metric BANDWIDTH

Requiere CF_TOKEN en .env (mismo que usa loader_cloudflare.py).
"""

import os
import csv
import time
import argparse
import calendar
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

CF_TOKEN = os.getenv("CF_TOKEN")
BASE_URL = "https://api.cloudflare.com/client/v4/radar/quality/iqi/summary"

# 35 países soberanos de América
AMERICAS = [
    # (code, name)
    ("CA", "Canada"),
    ("US", "United States"),
    ("MX", "México"),
    ("GT", "Guatemala"),
    ("BZ", "Belize"),
    ("HN", "Honduras"),
    ("SV", "El Salvador"),
    ("NI", "Nicaragua"),
    ("CR", "Costa Rica"),
    ("PA", "Panamá"),
    ("CU", "Cuba"),
    ("JM", "Jamaica"),
    ("HT", "Haití"),
    ("DO", "República Dominicana"),
    ("TT", "Trinidad y Tobago"),
    ("BB", "Barbados"),
    ("LC", "Santa Lucía"),
    ("VC", "San Vicente"),
    ("GD", "Granada"),
    ("AG", "Antigua y Barbuda"),
    ("DM", "Dominica"),
    ("KN", "San Cristóbal y Nieves"),
    ("BS", "Bahamas"),
    ("CO", "Colombia"),
    ("VE", "Venezuela"),
    ("GY", "Guyana"),
    ("SR", "Surinam"),
    ("BR", "Brasil"),
    ("PE", "Perú"),
    ("EC", "Ecuador"),
    ("BO", "Bolivia"),
    ("PY", "Paraguay"),
    ("CL", "Chile"),
    ("AR", "Argentina"),
    ("UY", "Uruguay"),
]


def add_months(dt: datetime, n: int) -> datetime:
    """Suma n meses a un datetime sin dependencias externas."""
    month = dt.month - 1 + n
    year  = dt.year + month // 12
    month = month % 12 + 1
    day   = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def month_ranges(start: datetime, end: datetime):
    """Genera tuplas (date_start_iso, date_end_iso, label) mes a mes."""
    current = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while current < end:
        last_day = calendar.monthrange(current.year, current.month)[1]
        month_end = current.replace(day=last_day, hour=23, minute=59, second=59)
        if month_end > end:
            month_end = end
        yield (
            current.strftime("%Y-%m-%dT%H:%M:%SZ"),
            month_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            current.strftime("%Y-%m"),
        )
        current = add_months(current, 1)


def fetch_iqi(code: str, date_start: str, date_end: str, metric: str,
              max_retries: int = 3) -> dict | None:
    """
    Llama al endpoint de Cloudflare Radar IQI summary para un país y rango
    de fechas absoluto. Reintenta automáticamente ante timeouts o errores
    de red transitorios (backoff exponencial: 2s, 4s, 8s).

    El parámetro de filtro por país es 'location' (SIN '[]' en el nombre).
    Enviar 'location[]' como clave literal hace que Cloudflare ignore el
    filtro y devuelva el agregado global — todos los países salen con el
    mismo valor. Ese era el bug original de este script.
    """
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(
                BASE_URL,
                headers={"Authorization": f"Bearer {CF_TOKEN}"},
                params={
                    "location":  code,
                    "dateStart": date_start,
                    "dateEnd":   date_end,
                    "metric":    metric,
                },
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                wait = 2 ** attempt
                print(f"    ⏳ {code}: {type(e).__name__}, reintentando en {wait}s "
                      f"(intento {attempt}/{max_retries})")
                time.sleep(wait)
                continue
            print(f"    ⚠ {code}: falló tras {max_retries} intentos — {e}")
            return None

        if not r.ok:
            print(f"    ⚠ HTTP {r.status_code} — {code}")
            return None

        data = r.json()
        if not data.get("success"):
            print(f"    ⚠ API error — {code}: {data.get('errors')}")
            return None

        # Cloudflare Radar devuelve el summary bajo "summary_0" o "summary 0"
        # Ajusta esta línea si tu loader usa una clave diferente:
        summary = (
            data.get("result", {}).get("summary_0")
            or data.get("result", {}).get("summary 0")
        )
        return summary

    return None


def main():
    parser = argparse.ArgumentParser(description="Descarga histórico IQI Cloudflare → CSV")
    parser.add_argument("--start",  default="2024-01-01",
                        help="Fecha inicio YYYY-MM-DD (default: 2024-01-01)")
    parser.add_argument("--end",    default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        help="Fecha fin YYYY-MM-DD (default: hoy)")
    parser.add_argument("--metric", default="LATENCY",
                        choices=["LATENCY", "BANDWIDTH", "DNS_RESPONSE_TIME"],
                        help="Métrica a descargar (default: LATENCY)")
    parser.add_argument("--output", default="historical_iqi.csv",
                        help="Nombre del CSV de salida. Si ya existe (de una corrida "
                             "anterior interrumpida), se reanuda: se omiten las "
                             "combinaciones mes+país ya presentes.")
    parser.add_argument("--delay",  type=float, default=0.15,
                        help="Segundos entre requests (default: 0.15)")
    args = parser.parse_args()

    if not CF_TOKEN:
        print("❌ CF_TOKEN no encontrado en .env")
        return

    start_dt = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt   = datetime.strptime(args.end,   "%Y-%m-%d").replace(tzinfo=timezone.utc)

    ranges = list(month_ranges(start_dt, end_dt))
    total  = len(ranges) * len(AMERICAS)
    done   = 0

    fieldnames = ["month", "date_start", "date_end", "country_code",
                  "country_name", "p25_ms", "p50_ms", "p75_ms", "metric"]

    # Reanudar: si ya existe un CSV parcial de una corrida anterior cortada,
    # saltamos las combinaciones (mes, país) que ya están escritas.
    already_done = set()
    file_exists = os.path.exists(args.output)
    if file_exists:
        with open(args.output, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                already_done.add((row["month"], row["country_code"]))
        if already_done:
            print(f"↻ Reanudando: {len(already_done)} combinaciones ya en {args.output}, se omiten.\n")

    print(f"Descargando {len(ranges)} meses × {len(AMERICAS)} países = {total} requests")
    print(f"Métrica: {args.metric} | Output: {args.output}\n")

    mode = "a" if file_exists else "w"
    with open(args.output, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        got_any = bool(already_done)
        for date_start, date_end, label in ranges:
            print(f"[{label}]")
            for code, name in AMERICAS:
                done += 1
                if (label, code) in already_done:
                    continue

                summary = fetch_iqi(code, date_start, date_end, args.metric)

                if summary:
                    writer.writerow({
                        "month":        label,
                        "date_start":   date_start,
                        "date_end":     date_end,
                        "country_code": code,
                        "country_name": name,
                        "p25_ms":       summary.get("p25"),
                        "p50_ms":       summary.get("p50"),
                        "p75_ms":       summary.get("p75"),
                        "metric":       args.metric,
                    })
                    f.flush()  # persistir en disco de inmediato, no solo al cerrar el archivo
                    got_any = True
                    print(f"  ✓ {code:2s}  p50={summary.get('p50')}")
                else:
                    print(f"  — {code:2s}  sin datos")

                time.sleep(args.delay)

    if not got_any:
        print("\n⚠ No se obtuvieron datos. Revisa CF_TOKEN y la estructura de respuesta.")
        return

    with open(args.output, newline="", encoding="utf-8") as f:
        final_rows = list(csv.DictReader(f))

    print(f"\n✓ {len(final_rows)} filas totales en {args.output}")
    print(f"  Países con datos: {len({r['country_code'] for r in final_rows})}/{len(AMERICAS)}")
    print(f"  Rango: {final_rows[0]['month']} → {final_rows[-1]['month']}")


if __name__ == "__main__":
    main()
