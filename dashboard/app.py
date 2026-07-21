"""
GeoGame Server Monitor — Dashboard
-----------------------------------
Mapa 2D interactivo (pydeck / deck.gl) de latencia de red en América +
panel de análisis sincronizado bidireccionalmente: clic en el mapa filtra
las métricas, clic en el ranking resalta el país en el mapa.
"""

import os

import pandas as pd
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="GeoGame Monitor",
    page_icon="🎮",
    layout="wide",
)

# ── Paleta ─────────────────────────────────────────────────────────────────
COLOR_LOW    = "#2ECC71"   # latencia baja
COLOR_MID    = "#F5A623"   # latencia media
COLOR_HIGH   = "#E74C3C"   # latencia alta
COLOR_ACCENT = "#7C3AED"   # selección activa
BG_CARD      = "rgba(255,255,255,0.03)"

LATENCY_SCALE = [
    [0.0, COLOR_LOW],
    [0.5, COLOR_MID],
    [1.0, COLOR_HIGH],
]


# ── Estado compartido (mapa ↔ dashboard) ────────────────────────────────────
if "selected_country" not in st.session_state:
    st.session_state.selected_country = None
if "selected_subregion" not in st.session_state:
    st.session_state.selected_subregion = None


def select_country(code: str | None):
    st.session_state.selected_country = code


def select_subregion(name: str | None):
    st.session_state.selected_subregion = name
    st.session_state.selected_country = None  # limpiar selección puntual


# ── Data fetching ──────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_json(endpoint: str, params: dict | None = None):
    r = requests.get(f"{API_URL}{endpoint}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=300)
def fetch_geojson():
    r = requests.get(f"{API_URL}/geo/americas", timeout=15)
    r.raise_for_status()
    return r.json()


col_title, col_btn = st.columns([5, 1])
with col_title:
    st.title("🎮 GeoGame Server Monitor")
    st.caption(
        "Latencia de red por país en América · Cloudflare Radar IQI · "
        "Tópicos Especiales II · UTP"
    )
with col_btn:
    st.write("")
    if st.button("🔄 Refrescar", use_container_width=True):
        st.cache_data.clear()
        st.session_state.selected_country = None
        st.session_state.selected_subregion = None
        st.rerun()

try:
    summary_data = fetch_json("/iqi/summary")
    history_data = fetch_json("/iqi/history")
    subregion_data = fetch_json("/iqi/by-subregion")
    geojson = fetch_geojson()
except requests.RequestException as e:
    st.error(f"❌ No se puede conectar con la API en `{API_URL}`. Error: {e}")
    st.stop()

df = pd.DataFrame(summary_data)
df_hist = pd.DataFrame(history_data)
df_sub = pd.DataFrame(subregion_data)

if df.empty:
    st.warning("No hay datos en `/iqi/summary` todavía. Corre los loaders primero.")
    st.stop()

df_hist["captured_at"] = pd.to_datetime(df_hist["captured_at"], utc=True).dt.tz_localize(None)
df_hist["month"] = df_hist["captured_at"].dt.to_period("M").astype(str)

# métrica visible: última medición si existe, si no el promedio
df["display_p50"] = df["latest_p50_ms"].fillna(df["avg_p50_ms"])


# ── Sidebar: filtros + consulta espacial ────────────────────────────────────
with st.sidebar:
    st.header("Filtros")

    subregiones = ["Todas"] + sorted(df["subregion"].dropna().unique().tolist())
    current_sub = st.session_state.selected_subregion or "Todas"
    picked_sub = st.selectbox("Subregión", subregiones, index=subregiones.index(current_sub) if current_sub in subregiones else 0)
    if picked_sub != current_sub:
        select_subregion(None if picked_sub == "Todas" else picked_sub)
        st.rerun()

    if st.session_state.selected_country:
        row = df[df["country"] == st.session_state.selected_country]
        name = row.iloc[0]["name"] if not row.empty else st.session_state.selected_country
        st.success(f"📍 País seleccionado: **{name}**")
        if st.button("Quitar selección", use_container_width=True):
            select_country(None)
            st.rerun()

    st.divider()
    st.header("🔍 Consulta espacial")
    st.caption("`GET /locations/radius` → `ST_DWithin` PostGIS")
    ref_lat = st.number_input("Latitud", value=9.0, step=0.5, format="%.4f")
    ref_lon = st.number_input("Longitud", value=-79.5, step=0.5, format="%.4f")
    radius_km = st.slider("Radio (km)", 100, 8000, 1500, step=100)

    if st.button("Ejecutar consulta", use_container_width=True):
        try:
            r = requests.get(
                f"{API_URL}/locations/radius",
                params={"lat": ref_lat, "lon": ref_lon, "dist": radius_km},
                timeout=10,
            )
            r.raise_for_status()
            df_rad = pd.DataFrame(r.json())
            if df_rad.empty:
                st.info("Sin resultados en ese radio.")
            else:
                st.success(f"{len(df_rad)} país(es) encontrado(s)")
                st.dataframe(
                    df_rad[["name", "country", "distance_km"]],
                    use_container_width=True,
                    hide_index=True,
                )
        except Exception as e:
            st.error(f"Error: {e}")


# ── Aplicar filtros de subregión al frame base ──────────────────────────────
df_view = df.copy()
if st.session_state.selected_subregion:
    df_view = df_view[df_view["subregion"] == st.session_state.selected_subregion]


# ── Layout principal: mapa | panel de análisis ──────────────────────────────
col_map, col_stats = st.columns([3, 2], gap="medium")

def latency_to_rgba(value: float, vmin: float, vmax: float) -> list[int]:
    """Interpola verde → naranja → rojo según percentil de latencia."""
    if pd.isna(value) or vmax <= vmin:
        return [128, 128, 128, 160]
    t = (value - vmin) / (vmax - vmin)
    t = min(max(t, 0.0), 1.0)
    if t < 0.5:
        t2 = t / 0.5
        r = int(46 + (245 - 46) * t2)
        g = int(204 + (166 - 204) * t2)
        b = int(113 + (35 - 113) * t2)
    else:
        t2 = (t - 0.5) / 0.5
        r = int(245 + (231 - 245) * t2)
        g = int(166 + (76 - 166) * t2)
        b = int(35 + (60 - 35) * t2)
    return [r, g, b, 235]


with col_map:
    st.subheader("Mapa de latencia — América")
    st.caption("Arrastra para moverte, scroll/pellizco para zoom · clic en un punto para filtrar el panel")

    vmin, vmax = float(df["display_p50"].min()), float(df["display_p50"].max())

    df_map = df_view.copy()
    df_map["fill_color"] = df_map["display_p50"].apply(lambda v: latency_to_rgba(v, vmin, vmax))
    df_map["radius_m"] = df_map.apply(
        lambda r: 65000 if r["country"] == st.session_state.selected_country
        else (45000 if r["is_focus"] else 30000),
        axis=1,
    )
    df_map["line_color"] = df_map["country"].apply(
        lambda c: [255, 255, 255, 255] if c == st.session_state.selected_country else [20, 20, 20, 120]
    )
    df_map["line_width"] = df_map["country"].apply(
        lambda c: 3 if c == st.session_state.selected_country else 1
    )

    geo_layer = pdk.Layer(
        "GeoJsonLayer",
        id="fronteras",
        data=geojson,
        stroked=True,
        filled=True,
        get_fill_color=[124, 58, 237, 12],
        get_line_color=[255, 255, 255, 55],
        line_width_min_pixels=1,
        pickable=False,
    )

    points_layer = pdk.Layer(
        "ScatterplotLayer",
        id="paises",
        data=df_map,
        get_position="[longitude, latitude]",
        get_fill_color="fill_color",
        get_line_color="line_color",
        get_line_width="line_width",
        line_width_min_pixels=1,
        get_radius="radius_m",
        radius_min_pixels=6,
        radius_max_pixels=40,
        pickable=True,
        auto_highlight=True,
        stroked=True,
    )

    view_state = pdk.ViewState(latitude=8.0, longitude=-75.0, zoom=2.3, pitch=0)

    deck = pdk.Deck(
        layers=[geo_layer, points_layer],
        initial_view_state=view_state,
        map_style=None,  # usa el estilo claro/oscuro del tema activo de Streamlit
        tooltip={
            "html": (
                "<b>{name}</b> ({country})<br/>"
                "Capital: {capital}<br/>"
                "Latencia p50: {display_p50} ms<br/>"
                "Mediciones: {measurement_count}"
            ),
            "style": {"backgroundColor": "#1a1a2e", "color": "white"},
        },
    )

    map_event = st.pydeck_chart(
        deck,
        on_select="rerun",
        selection_mode="single-object",
        key="main_map",
        height=560,
    )

    # Sync: clic en el mapa -> selecciona país
    if map_event and map_event.selection and map_event.selection.get("objects", {}).get("paises"):
        clicked = map_event.selection["objects"]["paises"][0]
        clicked_code = clicked.get("country")
        if clicked_code and clicked_code != st.session_state.selected_country:
            select_country(clicked_code)
            st.rerun()

    st.caption("🟢 baja · 🟠 media · 🔴 alta latencia · el punto crece si el país es foco o está seleccionado")


with col_stats:
    tab_rank, tab_heat, tab_region = st.tabs(["🏆 Ranking", "🗓️ Histórico", "🌎 Subregiones"])

    # ── Ranking por barras (sincronizado) ───────────────────────────────
    with tab_rank:
        st.caption("Clic en una barra para resaltar ese país en el mapa")

        df_rank = df_view.dropna(subset=["display_p50"]).sort_values("display_p50", ascending=True)
        bar_colors = [
            COLOR_ACCENT if c == st.session_state.selected_country else
            (COLOR_HIGH if v > df["display_p50"].quantile(0.66) else
             COLOR_MID if v > df["display_p50"].quantile(0.33) else COLOR_LOW)
            for c, v in zip(df_rank["country"], df_rank["display_p50"])
        ]

        fig_bar = go.Figure(
            go.Bar(
                x=df_rank["display_p50"],
                y=df_rank["name"],
                orientation="h",
                marker_color=bar_colors,
                customdata=df_rank["country"],
                text=df_rank["display_p50"].map(lambda v: f"{v:.0f} ms"),
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>%{x} ms<extra></extra>",
            )
        )
        fig_bar.update_layout(
            height=max(320, 24 * len(df_rank)),
            margin=dict(l=0, r=30, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="latencia p50 (ms)",
            yaxis=dict(autorange="reversed"),
            font=dict(size=11),
        )

        bar_event = st.plotly_chart(
            fig_bar,
            use_container_width=True,
            on_select="rerun",
            selection_mode="points",
            key="rank_bar",
        )
        if bar_event and bar_event.get("selection", {}).get("points"):
            idx = bar_event["selection"]["points"][0].get("point_index")
            if idx is not None:
                clicked_code = df_rank.iloc[idx]["country"]
                if clicked_code != st.session_state.selected_country:
                    select_country(clicked_code)
                    st.rerun()

        best = df_rank.iloc[0]
        worst = df_rank.iloc[-1]
        c1, c2 = st.columns(2)
        c1.metric("🟢 Menor latencia", best["country"], f"{best['display_p50']:.0f} ms")
        c2.metric("🔴 Mayor latencia", worst["country"], f"{worst['display_p50']:.0f} ms")

        pa_row = df[df["country"] == "PA"]
        if not pa_row.empty and pd.notna(pa_row.iloc[0]["display_p50"]):
            pa_val = pa_row.iloc[0]["display_p50"]
            rank_pos = int((df["display_p50"] > pa_val).sum()) + 1
            st.info(
                f"**Panamá:** {pa_val:.0f} ms (p50) — posición **{rank_pos}/{len(df)}** "
                f"en el ranking de latencia (1 = mejor)."
            )

    # ── Heatmap temporal país × mes ─────────────────────────────────────
    with tab_heat:
        st.caption("Concentración de latencia por país a lo largo del tiempo")

        df_heat_src = df_hist if not st.session_state.selected_subregion else df_hist[
            df_hist["subregion"] == st.session_state.selected_subregion
        ]

        if df_heat_src.empty:
            st.info("Sin histórico para esta selección.")
        else:
            pivot = df_heat_src.pivot_table(
                index="name", columns="month", values="p50_ms", aggfunc="mean"
            )
            # ordenar filas por promedio descendente (peor arriba)
            pivot = pivot.loc[pivot.mean(axis=1).sort_values(ascending=False).index]

            fig_heat = go.Figure(
                go.Heatmap(
                    z=pivot.values,
                    x=pivot.columns,
                    y=pivot.index,
                    colorscale=LATENCY_SCALE,
                    colorbar=dict(title="p50 (ms)", thickness=14),
                    hovertemplate="%{y} · %{x}<br>%{z:.0f} ms<extra></extra>",
                )
            )
            fig_heat.update_layout(
                height=max(320, 22 * len(pivot)),
                margin=dict(l=0, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(size=10),
            )
            st.plotly_chart(fig_heat, use_container_width=True, key="heatmap")

    # ── Agregado por subregión ───────────────────────────────────────────
    with tab_region:
        st.caption("Clic en una barra para filtrar el mapa y el ranking por subregión")

        if df_sub.empty:
            st.info("Sin datos por subregión.")
        else:
            df_sub_sorted = df_sub.sort_values("avg_p50_ms", ascending=True)
            reg_colors = [
                COLOR_ACCENT if r == st.session_state.selected_subregion else "#5B8DEF"
                for r in df_sub_sorted["subregion"]
            ]
            fig_reg = go.Figure(
                go.Bar(
                    x=df_sub_sorted["avg_p50_ms"],
                    y=df_sub_sorted["subregion"],
                    orientation="h",
                    marker_color=reg_colors,
                    text=df_sub_sorted["avg_p50_ms"].map(lambda v: f"{v:.0f} ms"),
                    textposition="outside",
                    customdata=df_sub_sorted["country_count"],
                    hovertemplate="<b>%{y}</b><br>%{x} ms promedio<br>%{customdata} países<extra></extra>",
                )
            )
            fig_reg.update_layout(
                height=260,
                margin=dict(l=0, r=30, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis_title="latencia p50 promedio (ms)",
                font=dict(size=11),
            )
            reg_event = st.plotly_chart(
                fig_reg,
                use_container_width=True,
                on_select="rerun",
                selection_mode="points",
                key="region_bar",
            )
            if reg_event and reg_event.get("selection", {}).get("points"):
                idx = reg_event["selection"]["points"][0].get("point_index")
                if idx is not None:
                    clicked_region = df_sub_sorted.iloc[idx]["subregion"]
                    new_val = None if clicked_region == st.session_state.selected_subregion else clicked_region
                    select_subregion(new_val)
                    st.rerun()

            st.dataframe(
                df_sub_sorted.rename(columns={
                    "subregion": "Subregión",
                    "country_count": "Países",
                    "measurement_count": "Mediciones",
                    "avg_p50_ms": "p50 promedio (ms)",
                }),
                use_container_width=True,
                hide_index=True,
            )


# ── Detalle del país seleccionado ───────────────────────────────────────────
if st.session_state.selected_country:
    sel_row = df[df["country"] == st.session_state.selected_country]
    if not sel_row.empty:
        sel_row = sel_row.iloc[0]
        st.divider()
        st.subheader(f"📍 Detalle — {sel_row['name']} ({sel_row['country']})")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Última p50", f"{sel_row['display_p50']:.0f} ms" if pd.notna(sel_row['display_p50']) else "—")
        m2.metric("Promedio histórico", f"{sel_row['avg_p50_ms']:.0f} ms" if pd.notna(sel_row['avg_p50_ms']) else "—")
        m3.metric("Mínimo registrado", f"{sel_row['min_p50_ms']:.0f} ms" if pd.notna(sel_row['min_p50_ms']) else "—")
        m4.metric("Mediciones totales", int(sel_row["measurement_count"]))

        df_sel_hist = df_hist[df_hist["country"] == st.session_state.selected_country].sort_values("captured_at")
        if not df_sel_hist.empty:
            fig_line = px.line(
                df_sel_hist, x="captured_at", y=["p25_ms", "p50_ms", "p75_ms"],
                labels={"captured_at": "fecha", "value": "latencia (ms)", "variable": "percentil"},
            )
            fig_line.update_layout(
                height=280,
                margin=dict(l=0, r=0, t=20, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_line, use_container_width=True, key="detail_line")
