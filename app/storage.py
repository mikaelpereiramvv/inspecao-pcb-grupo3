"""Storage de imagens (Bloco 4 da Figura 1).

Mitigação do risco "Dessincronização banco × disco" (Seção 12, Arq. v1):
a imagem é gravada com ID único (UUID) e sincronizada no disco ANTES do commit
no banco relacional. Se o commit falhar, a imagem órfã é removida.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from pathlib import Path


# original = imagem recebida (resolução da câmera); exibicao = 600×600 padronizada
# (referência das coordenadas no banco); anotada = exibicao + marcações
SUFIXOS = ("original", "exibicao", "anotada")


class Storage:
    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)

    def novo_id(self) -> str:
        return uuid.uuid4().hex

    def caminho(self, id_imagem: str, sufixo: str) -> Path:
        if not id_imagem.isalnum():
            raise ValueError("ID de imagem inválido")
        if sufixo not in SUFIXOS:
            raise ValueError("Sufixo inválido")
        return self.pasta / id_imagem[:2] / f"{id_imagem}_{sufixo}.png"

    def gravar(self, id_imagem: str, sufixo: str, conteudo: bytes) -> Path:
        destino = self.caminho(id_imagem, sufixo)
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            f.write(conteudo)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, destino)  # renomeação atômica
        return destino

    def ler(self, id_imagem: str, sufixo: str) -> bytes:
        return self.caminho(id_imagem, sufixo).read_bytes()

    def remover(self, id_imagem: str) -> None:
        for suf in SUFIXOS:
            p = self.caminho(id_imagem, suf)
            if p.exists():
                p.unlink()

    @contextmanager
    def transacao(self, id_imagem: str):
        """Uso: grava as imagens dentro do bloco e faz o commit no banco no fim.
        Qualquer exceção remove os arquivos gravados (sem registros órfãos)."""
        try:
            yield
        except BaseException:
            self.remover(id_imagem)
            raise
