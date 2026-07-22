import os
import requests
from mage_ai.data_preparation.decorators import data_loader, test

PAISES = {
    "AG": "Antigua y Barbuda", "AR": "Argentina", "BB": "Barbados",
    "BO": "Bolivia", "BR": "Brasil", "BS": "Bahamas", "BZ": "Belice",
    "CA": "Canadá", "CL": "Chile", "CO": "Colombia", "CR": "Costa Rica",
    "CU": "Cuba", "DM": "Dominica", "DO": "República Dominicana",
    "EC": "Ecuador", "SV": "El Salvador", "GD": "Granada",
    "GT": "Guatemala", "GY": "Guyana", "HN": "Honduras", "HT": "Haití",
    "JM": "Jamaica", "KN": "San Cristóbal y Nieves", "LC": "Santa Lucía",
    "MX": "México", "NI": "Nicaragua", "PA": "Panamá", "PE": "Perú",
    "PY": "Paraguay", "SR": "Surinam", "TT": "Trinidad y Tobago",
    "US": "Estados Unidos", "UY": "Uruguay", "VC": "San Vicente y las Granadinas",
    "VE": "Venezuela",
}


@data_loader
def load_data(*args, **kwargs):
    # Leer token desde variables de Mage o desde env
    token = kwargs.get("CF_TOKEN") or os.getenv("CF_TOKEN")
    if not token:
        raise RuntimeError(
            "CF_TOKEN no está definido. "
            "Agrégalo en Mage: Settings → Variables → CF_TOKEN"
        )

    headers = {"Authorization": f"Bearer {token}"}
    BASE = "https://api.cloudflare.com/client/v4"
    rows = []

    for code, nombre in PAISES.items():
        try:
            r = requests.get(
                f"{BASE}/radar/quality/iqi/summary",
                headers=headers,
                params={"metric": "LATENCY", "location": code, "dateRange": "7d"},
                timeout=30,
            )
            data = r.json()

            if not data.get("success"):
                print(f"  {nombre} ({code}) — API error: {data.get('errors')}")
                continue

            result = data.get("result")
            if not result:
                print(f"  {nombre} ({code}) — sin resultado")
                continue

            s = result.get("summary_0")
            if not s:
                print(f"  {nombre} ({code}) — summary_0 vacío")
                continue

            rows.append({
                "location_code": code,
                "metric": "LATENCY",
                "p25": float(s["p25"]),
                "p50": float(s["p50"]),
                "p75": float(s["p75"]),
                "date_range": "7d",
            })
            print(f"  ✓ {nombre} ({code})  p50={s['p50']}")

        except Exception as e:
            print(f"  ✗ {nombre} ({code}) — {e}")

    print(f"\nTotal: {len(rows)}/{len(PAISES)} países capturados")
    return rows


@test
def test_output(output, *args):
    assert output is not None, "El loader no devolvió nada"
    assert isinstance(output, list), "Se esperaba una lista"
    assert len(output) > 0, "Lista vacía — revisar token o respuesta de Cloudflare"
