#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import pandas as pd

def prepare_for_kepler(input_csv, output_csv):
    """Adapta o CSV com colunas formatadas para o Kepler.gl e Deck.gl TripsLayer."""
    print(f"Lendo {input_csv}...")
    df = pd.read_csv(input_csv)
    
    # Formata campos explicitamente
    df = df[['trip_id', 'timestamp', 'lat', 'lon', 'seconds']]
    df.to_csv(output_csv, index=False)
    print(f"Arquivo preparado para Kepler.gl salvo em: {output_csv}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Prepara CSV de posições para o Kepler.gl.")
    parser.add_argument("--input", type=str, default="onibus_mg_minuto.csv", help="CSV de posições")
    parser.add_argument("--output", type=str, default="kepler_onibus_mg.csv", help="CSV pronto para upload")
    args = parser.parse_args()

    prepare_for_kepler(args.input, args.output)
