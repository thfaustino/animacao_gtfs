# Animação GTFS - Posição dos Ônibus por Minuto (Minas Gerais)

Projeto para interpolação temporal de feeds GTFS Schedule e renderização de vídeo animado com a frota em movimento minuto a minuto.

## 📁 Estrutura do Projeto

```
gtfs-animacao-mg/
├── interpolate_gtfs.py       # Script de interpolação dos dados GTFS para CSV temporal
├── render_animation.py       # Renderiza o arquivo CSV em vídeo MP4 usando Matplotlib
├── export_kepler.py          # Utilitário para exportar no formato ideal para Kepler.gl / Deck.gl
├── sample_data/              # Pasta para posicionar seu arquivo GTFS (.zip)
│   └── README.txt
├── requirements.txt          # Dependências Python
└── README.md                 # Documentação e instruções de execução
```

## 🚀 Como Executar

### 1. Instalar as Dependências

```bash
pip install -r requirements.txt
```

> **Atenção:** Para renderizar vídeos `.mp4` com o Matplotlib, é necessário ter o `ffmpeg` instalado no sistema operacional (`sudo apt install ffmpeg` no Linux, `brew install ffmpeg` no macOS ou via instalador no Windows).

---

### 2. Inserir os Dados GTFS

Coloque o seu arquivo `.zip` (por exemplo, `gtfs_mg.zip`) na pasta raiz ou em `sample_data/`.

---

### 3. Gerar as Posições Minuto a Minuto

Execute o script de interpolação:

```bash
python interpolate_gtfs.py --gtfs seu_arquivo_gtfs.zip --output onibus_mg_minuto.csv
```

Opções:
* `--step 60`: intervalo de amostragem em segundos (padrão: 60s = 1 minuto).
* `--service-id`: (opcional) filtra um calendário específico (ex.: dias úteis).

---

### 4. Gerar o Vídeo Animado

Com o arquivo `onibus_mg_minuto.csv` gerado:

```bash
python render_animation.py --input onibus_mg_minuto.csv --output animacao_onibus_mg.mp4 --fps 20
```

---

### 5. (Opcional) Visualização Interativa Web (Kepler.gl)

Se preferir uma visualização interativa acelerada por GPU sem renderizar vídeo local:

```bash
python export_kepler.py --input onibus_mg_minuto.csv --output kepler_ready.csv
```

Em seguida, basta carregar o arquivo gerado diretamente no [kepler.gl](https://kepler.gl/) e habilitar o filtro temporal.
