"""Treina o detector de defeitos conhecidos (Seção 8, componente 2).

Decisão aberta 9.1: a variante exata depende da GPU do grupo. Exemplos:
  --modelo yolov10s.pt  (YOLOv10 Small, como Mitoso e Melo, 2025 — sem a Ghost Convolution)
  --modelo yolov8n.pt   (mais leve)
  --modelo yolo11s.pt
A versão com Ghost Convolution exige o YAML de arquitetura dos autores: passe-o em --modelo.

Uso:
  python scripts/treinar_yolo.py --dados datasets/pcb/pcb.yaml --modelo yolov10s.pt --epocas 100
O melhor peso é copiado para modelos/yolo_pcb.pt (caminho lido pela aplicação).
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from _comum import RAIZ


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dados", required=True, type=Path)
    ap.add_argument("--modelo", default="yolov10s.pt")
    ap.add_argument("--epocas", type=int, default=100)
    # 600 px não é múltiplo de 32; o YOLO arredonda para 608
    ap.add_argument("--imgsz", type=int, default=608)
    ap.add_argument("--lote", type=int, default=16)
    ap.add_argument("--dispositivo", default=None, help="ex.: 0 (GPU) ou cpu")
    ap.add_argument("--projeto", default=str(RAIZ / "runs"))
    ap.add_argument("--nome", default="pcb")
    ap.add_argument("--paciencia", type=int, default=20)
    a = ap.parse_args()

    from ultralytics import YOLO

    modelo = YOLO(a.modelo)
    modelo.train(data=str(a.dados), epochs=a.epocas, imgsz=a.imgsz, batch=a.lote, device=a.dispositivo,
                 project=a.projeto, name=a.nome, patience=a.paciencia, exist_ok=True,
                 # o pipeline de inspeção não espelha nem gira a placa: aumentos geométricos leves
                 fliplr=0.5, flipud=0.5, degrees=0.0, mosaic=1.0)
    melhor = Path(a.projeto) / a.nome / "weights" / "best.pt"
    destino = RAIZ / "modelos" / "yolo_pcb.pt"
    destino.parent.mkdir(exist_ok=True)
    shutil.copy2(melhor, destino)
    print(f"Peso final copiado para {destino}")


if __name__ == "__main__":
    main()
