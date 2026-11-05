#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import zipfile
from datetime import timedelta
import pandas as pd
import numpy as np
from shapely.geometry import LineString, Point
from tqdm import tqdm

def time_to_seconds(time_str):
    """Converte 'HH:MM:SS' para segundos desde o início do dia."""
    # Alguns feeds exportam o horário como fração do dia (ex.: 0.5 = 12:00:00)
    if not isinstance(time_str, str):
        return int(round(float(time_str) * 86400))
    time_str = time_str.strip()
    if ':' not in time_str:
        return int(round(float(time_str) * 86400))
    parts = time_str.split(':')
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    return h * 3600 + m * 60 + s

def load_gtfs_tables(zip_path):
    """Carrega tabelas essenciais a partir do arquivo GTFS compactado."""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        trips = pd.read_csv(z.open('trips.txt'))
        stop_times = pd.read_csv(z.open('stop_times.txt'))
        stops = pd.read_csv(z.open('stops.txt'))
        shapes = pd.read_csv(z.open('shapes.txt')) if 'shapes.txt' in names else None
        calendar = pd.read_csv(z.open('calendar.txt')) if 'calendar.txt' in names else None
    return trips, stop_times, stops, shapes, calendar

def active_service_ids(date, calendar):
    """Retorna os service_id (como str) do calendário regular ativos no dia da semana de 'date'.

    Ignora calendar_dates.txt (exceções) e a validade start_date/end_date.
    """
    weekday = date.strftime('%A').lower()
    return set(calendar.loc[calendar[weekday] == 1, 'service_id'].astype(str))

def haversine_km(lon1, lat1, lon2, lat2):
    """Distância em km entre pontos (aceita arrays)."""
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))

def build_shape_geometries(shapes_df):
    """Cria geometrias LineString a partir de shapes.txt e o fator km por unidade (grau) de cada shape."""
    if shapes_df is None:
        return {}, {}
    shapes_df = shapes_df.sort_values(by=['shape_id', 'shape_pt_sequence'])
    grouped = shapes_df.groupby('shape_id')
    shape_lines = {}
    km_per_unit = {}
    for shape_id, group in grouped:
        lons = group['shape_pt_lon'].values
        lats = group['shape_pt_lat'].values
        if len(lons) >= 2:
            line = LineString(zip(lons, lats))
            length_km = haversine_km(lons[:-1], lats[:-1], lons[1:], lats[1:]).sum()
            shape_lines[shape_id] = line
            km_per_unit[shape_id] = length_km / line.length if line.length > 0 else 0.0
    return shape_lines, km_per_unit

def enforce_max_speed(secs, km_pos, max_speed_kmh):
    """Atrasa as chegadas que exigiriam velocidade acima do limite entre paradas consecutivas.

    Corrige horários do feed com paradas distantes no mesmo minuto, que gerariam saltos no mapa.
    """
    secs = np.maximum.accumulate(np.asarray(secs, dtype=float))
    min_dt = np.diff(km_pos) / max_speed_kmh * 3600
    for i in range(1, len(secs)):
        secs[i] = max(secs[i], secs[i - 1] + min_dt[i - 1])
    return secs

def interpolate_trip(trip_df, shape_line, minute_step=60, base_date=None, offset=0,
                     km_per_unit=0.0, max_speed_kmh=100.0, max_stop_offset_km=5.0):
    """Interpola a posição de uma viagem a cada 'minute_step' segundos.

    'seconds' é contado desde o início do período (offset = segundos até o início do dia da viagem).
    trip_df já chega ordenado na ordem física das paradas, com horários crescentes.
    """
    lons = trip_df['stop_lon'].values
    lats = trip_df['stop_lat'].values
    known_secs = trip_df['sec'].values.astype(float)
    known_stops = [Point(lon, lat) for lon, lat in zip(lons, lats)]

    if shape_line is not None:
        # Descarta paradas com coordenada errada (muito longe do trajeto), que causariam saltos
        near = np.array([shape_line.distance(pt) * 105 <= max_stop_offset_km for pt in known_stops])
        if near.sum() < 2:
            return []
        known_stops = [pt for pt, ok in zip(known_stops, near) if ok]
        known_secs = known_secs[near]
        # Projeções não decrescentes: o ônibus nunca volta no trajeto
        known_dists = np.maximum.accumulate([shape_line.project(pt) for pt in known_stops])
        km_pos = known_dists * km_per_unit
    else:
        known_dists = None
        km_pos = np.concatenate([[0.0], np.cumsum(haversine_km(lons[:-1], lats[:-1], lons[1:], lats[1:]))])

    known_secs = enforce_max_speed(known_secs, km_pos, max_speed_kmh)

    t_start = int(known_secs.min())
    t_end = int(known_secs.max())
    start_minute = (t_start // minute_step) * minute_step
    end_minute = ((t_end // minute_step) + 1) * minute_step
    target_times = np.arange(start_minute, end_minute, minute_step)

    if known_dists is not None:
        interp_dists = np.interp(target_times, known_secs, known_dists)

    records = []
    trip_id = trip_df['trip_id'].iloc[0]
    
    for k, t in enumerate(target_times):
        if t < t_start or t > t_end:
            continue
        if shape_line is not None:
            pt = shape_line.interpolate(interp_dists[k])
            lon, lat = pt.x, pt.y
        else:
            idx = np.searchsorted(known_secs, t) - 1
            idx = max(0, min(idx, len(known_stops) - 2))
            dt = max(1, (known_secs[idx+1] - known_secs[idx]))
            ratio = min(1.0, max(0.0, (t - known_secs[idx]) / dt))
            lon = known_stops[idx].x + ratio * (known_stops[idx+1].x - known_stops[idx].x)
            lat = known_stops[idx].y + ratio * (known_stops[idx+1].y - known_stops[idx].y)
            
        ts = base_date + timedelta(seconds=int(t))
        records.append({
            'trip_id': trip_id,
            'timestamp': ts.strftime("%Y-%m-%d %H:%M:%S"),
            'seconds': int(t) + offset,
            'lon': round(lon, 6),
            'lat': round(lat, 6)
        })
    return records

def fill_terminal_coords(stop_times, trips, shapes):
    """Preenche lat/lon de paradas terminais ausentes em stops.txt usando o início/fim do shape da viagem.

    No feed, o primeiro ou o último stop_id de cada viagem (ex.: '45012' = Belo Horizonte) não existe em
    stops.txt. Quando o shape da viagem não existe, usa a mediana das coordenadas obtidas para o mesmo stop_id.
    """
    missing = stop_times['stop_lat'].isna()
    if not missing.any() or shapes is None:
        return stop_times
    sh = shapes.sort_values(['shape_id', 'shape_pt_sequence'])
    sh = sh.assign(shape_id=sh['shape_id'].astype(str))
    ends = sh.groupby('shape_id').agg(
        slat=('shape_pt_lat', 'first'), slon=('shape_pt_lon', 'first'),
        elat=('shape_pt_lat', 'last'), elon=('shape_pt_lon', 'last'))
    seq = stop_times.groupby('trip_id')['stop_sequence'].agg(smin='min', smax='max')
    info = stop_times.loc[missing, ['trip_id', 'stop_id', 'stop_sequence']].copy()
    info['shape_id'] = info['trip_id'].map(trips.drop_duplicates('trip_id').set_index('trip_id')['shape_id']).astype(str)
    info = info.join(seq, on='trip_id').join(ends, on='shape_id')
    is_first = info['stop_sequence'] == info['smin']
    is_last = info['stop_sequence'] == info['smax']
    info['lat'] = np.where(is_first, info['slat'], np.where(is_last, info['elat'], np.nan))
    info['lon'] = np.where(is_first, info['slon'], np.where(is_last, info['elon'], np.nan))
    median = info.groupby('stop_id')[['lat', 'lon']].median()
    for col in ('lat', 'lon'):
        info[col] = info[col].fillna(info['stop_id'].map(median[col]))
    stop_times.loc[info.index, 'stop_lat'] = info['lat']
    stop_times.loc[info.index, 'stop_lon'] = info['lon']
    return stop_times

def process_gtfs_to_minute_positions(gtfs_zip, output_csv="onibus_mg_minuto.csv", step=60, service_id=None, date=None, max_speed=100.0):
    print(f"Carregando tabelas GTFS de: {gtfs_zip}")
    trips, stop_times, stops, shapes, calendar = load_gtfs_tables(gtfs_zip)
    shapes_dict, km_per_unit = build_shape_geometries(shapes)
    day = pd.Timestamp(date).to_pydatetime().replace(hour=0, minute=0, second=0, microsecond=0)
    print(f"Dia de referência: {day:%d/%m/%Y} ({day:%A})")

    if service_id:
        print(f"Filtrando por service_id: {service_id}")
        trips = trips[trips['service_id'].astype(str) == str(service_id)]
        stop_times = stop_times[stop_times['trip_id'].isin(trips['trip_id'])]
        
    stop_times = stop_times.merge(stops[['stop_id', 'stop_lat', 'stop_lon']], on='stop_id', how='left')
    n_missing = int(stop_times['stop_lat'].isna().sum())
    stop_times = fill_terminal_coords(stop_times, trips, shapes)
    print(f"Paradas sem coordenada em stops.txt: {n_missing:,} (recuperadas pelo shape: {n_missing - int(stop_times['stop_lat'].isna().sum()):,})")
    # GTFS permite horários vazios em paradas intermediárias; usa departure_time como alternativa
    times = stop_times['arrival_time']
    if 'departure_time' in stop_times.columns:
        times = times.fillna(stop_times['departure_time'])
    stop_times['arrival_time'] = times
    stop_times = stop_times.dropna(subset=['arrival_time', 'stop_lat', 'stop_lon'])
    stop_times = stop_times.copy()
    stop_times['sec'] = stop_times['arrival_time'].apply(time_to_seconds)
    stop_times = stop_times.sort_values(['trip_id', 'stop_sequence'])
    # Desdobra a virada da meia-noite (23:59 -> 00:14 ou, nas viagens espelhadas, 00:14 -> 23:59)
    by_trip = stop_times.groupby('trip_id')['sec']
    step_sec = ((by_trip.diff() + 43200) % 86400) - 43200
    stop_times['sec'] = by_trip.transform('first') + step_sec.fillna(0).groupby(stop_times['trip_id']).cumsum()
    # As viagens de volta (direction_id=1) trazem stop_sequence e shape na ordem física correta (origem -> BH),
    # mas com horários espelhados (BH no menor horário). Espelha os horários para o sentido do stop_sequence.
    by_trip = stop_times.groupby('trip_id')['sec']
    reversed_trip = by_trip.transform('last') < by_trip.transform('first')
    mirrored = by_trip.transform('min') + by_trip.transform('max') - stop_times['sec']
    stop_times['sec'] = stop_times['sec'].where(~reversed_trip, mirrored).astype(int)
    # Mantém o início de cada viagem dentro do dia de serviço (0 <= início < 24h)
    stop_times['sec'] -= (stop_times.groupby('trip_id')['sec'].transform('min') // 86400) * 86400
    print(f"Viagens com horários espelhados corrigidos: {stop_times.loc[reversed_trip, 'trip_id'].nunique():,}")
    stop_times = stop_times.sort_values(['trip_id', 'stop_sequence'])
    stop_times = stop_times[stop_times.groupby('trip_id')['trip_id'].transform('size') >= 2]
    stop_times = stop_times.merge(trips[['trip_id', 'service_id', 'shape_id']], on='trip_id', how='left')
    stop_times['service_id'] = stop_times['service_id'].astype(str)

    def trips_of(d):
        active = active_service_ids(d, calendar)
        return stop_times[stop_times['service_id'].isin(active)], len(active)

    def interpolate_all(day_times, d, offset, label, keep):
        grouped = day_times.groupby('trip_id')
        print(f"{d:%d/%m/%Y} ({d:%A}) {label}: {len(grouped)} viagens")
        out = []
        for trip_id, trip_df in tqdm(grouped):
            shape_id = trip_df['shape_id'].iloc[0]
            shape_line = shapes_dict.get(shape_id, None)
            records = interpolate_trip(trip_df, shape_line, minute_step=step, base_date=d, offset=offset,
                                       km_per_unit=km_per_unit.get(shape_id, 0.0), max_speed_kmh=max_speed)
            out.extend(r for r in records if keep(r['seconds']))
        return out

    # Dia de referência: o vídeo termina às 23:59, então descarta o que passa da meia-noite.
    ref_times, n_active = trips_of(day)
    if ref_times.empty:
        raise SystemExit(f"Nenhum serviço ativo em {day:%d/%m/%Y} (verifique a validade do feed em calendar.txt).")
    all_positions = interpolate_all(ref_times, day, 0, f"(referência, {n_active} serviços)", lambda s: s < 86400)

    # Dia anterior: só viagens ainda em curso após a meia-noite, no início do vídeo.
    prev = day - timedelta(days=1)
    prev_times, _ = trips_of(prev)
    prev_times = prev_times[prev_times.groupby('trip_id')['sec'].transform('max') >= 86400]
    if not prev_times.empty:
        all_positions += interpolate_all(prev_times, prev, -86400, "(anterior, em curso após 24h)", lambda s: 0 <= s < 86400)

    df_out = pd.DataFrame(all_positions)
    df_out.to_csv(output_csv, index=False)
    print(f"Sucesso! {len(df_out):,} registros salvos em '{output_csv}'.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Interpola viagens de um GTFS a cada minuto.")
    parser.add_argument("--gtfs", type=str, required=True, help="Caminho para o arquivo GTFS (.zip)")
    parser.add_argument("--output", type=str, default="onibus_mg_minuto.csv", help="Nome do CSV de saída")
    parser.add_argument("--step", type=int, default=60, help="Passo de tempo em segundos (padrão: 60)")
    parser.add_argument("--service-id", type=str, default=None, help="service_id opcional para filtro")
    parser.add_argument("--date", type=str, required=True, help="Data de referência (AAAA-MM-DD)")
    parser.add_argument("--max-speed", type=float, default=100.0, help="Velocidade máxima (km/h) entre paradas; horários que exigiriam mais são atrasados (padrão: 100)")
    args = parser.parse_args()

    process_gtfs_to_minute_positions(args.gtfs, args.output, args.step, args.service_id, args.date, args.max_speed)
