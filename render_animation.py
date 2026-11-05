#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import shutil
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation

def ensure_ffmpeg():
    """Usa o ffmpeg do sistema ou, na falta dele, o binário do pacote imageio-ffmpeg."""
    if shutil.which('ffmpeg'):
        return
    try:
        import imageio_ffmpeg
        matplotlib.rcParams['animation.ffmpeg_path'] = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit("ffmpeg não encontrado. Instale com: pip install imageio-ffmpeg")

DIAS = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo']

def render_video(input_csv, output_video, fps=20, dpi=150, sample_interval=1, boundary_path=None):
    ensure_ffmpeg()
    print(f"Carregando dados de: {input_csv}...")
    df = pd.read_csv(input_csv)
    first = df.iloc[0]
    base_date = datetime.strptime(first['timestamp'], "%Y-%m-%d %H:%M:%S") - timedelta(seconds=int(first['seconds']))
    
    unique_times = sorted(df['seconds'].unique())
    if sample_interval > 1:
        unique_times = unique_times[::sample_interval]
        
    print(f"Total de quadros a renderizar: {len(unique_times)}")

    fig, ax = plt.subplots(figsize=(10, 10), facecolor='#0b0f19')
    ax.set_facecolor('#0b0f19')
    
    min_lon, max_lon, min_lat, max_lat = df['lon'].min(), df['lon'].max(), df['lat'].min(), df['lat'].max()
    if boundary_path:
        boundary = gpd.read_file(boundary_path).to_crs(epsg=4326)
        boundary.boundary.plot(ax=ax, color='#8e9aaf', linewidth=1.2)
        b_min_lon, b_min_lat, b_max_lon, b_max_lat = boundary.total_bounds
        min_lon, max_lon = min(min_lon, b_min_lon), max(max_lon, b_max_lon)
        min_lat, max_lat = min(min_lat, b_min_lat), max(max_lat, b_max_lat)
    lon_pad = (max_lon - min_lon) * 0.05
    lat_pad = (max_lat - min_lat) * 0.05
    ax.set_xlim(min_lon - lon_pad, max_lon + lon_pad)
    ax.set_ylim(min_lat - lat_pad, max_lat + lat_pad)
    ax.set_aspect('equal')
    ax.axis('off')
    
    scatter = ax.scatter([], [], c='#00f0ff', s=12, alpha=0.75, edgecolors='none')
    time_text = ax.text(
        0.04, 0.94, '',
        transform=ax.transAxes,
        color='#ffffff',
        fontsize=15,
        weight='bold',
        family='sans-serif'
    )
    
    title_text = ax.text(
        0.04, 0.90, '''Transporte Intermunicipal de Passageiros-MG''',
        transform=ax.transAxes,
        color='#8e9aaf',
        fontsize=10,
        family='sans-serif'
    )

    count_text = ax.text(
        0.04, 0.86, '',
        transform=ax.transAxes,
        color='#00f0ff',
        fontsize=12,
        family='sans-serif'
    )

    frames_by_sec = {sec: g[['lon', 'lat']].values for sec, g in df.groupby('seconds')}

    def update(frame_sec):
        coords = frames_by_sec[frame_sec]
        scatter.set_offsets(coords)
        
        ts = base_date + timedelta(seconds=int(frame_sec))
        time_text.set_text(f"{DIAS[ts.weekday()]}, {ts:%d/%m/%Y}  {ts:%H:%M}")
        # count_text.set_text(f"Viagens em operação: {len(coords):,}".replace(',', '.'))
        return scatter, time_text, count_text

    anim = animation.FuncAnimation(fig, update, frames=unique_times, blit=True, interval=1000 // fps)
    
    print(f"Renderizando vídeo para: {output_video} (FPS={fps}, DPI={dpi})...")
    anim.save(output_video, writer='ffmpeg', fps=fps, dpi=dpi)
    print("Renderização concluída com sucesso!")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Renderiza animação MP4 a partir das posições minuto a minuto.")
    parser.add_argument("--input", type=str, default="onibus_mg_minuto.csv", help="Caminho do CSV gerado")
    parser.add_argument("--output", type=str, default="animacao_onibus_mg.mp4", help="Arquivo de saída .mp4")
    parser.add_argument("--fps", type=int, default=20, help="Taxa de quadros por segundo")
    parser.add_argument("--dpi", type=int, default=150, help="Resolução do vídeo")
    parser.add_argument("--interval", type=int, default=1, help="Pular N quadros (ex: 2 para dobrar velocidade)")
    parser.add_argument("--boundary", type=str, default="zip://sample_data/limite_estado.zip", help="Shapefile (ou .zip) com o limite do estado; use '' para desativar")
    args = parser.parse_args()

    render_video(args.input, args.output, args.fps, args.dpi, args.interval, args.boundary or None)
