"""Geração de dados fictícios (cidades, veículos, descrições) a partir de um RNG injetado."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Cidade:
    """Cidade brasileira com coordenadas aproximadas."""

    nome: str
    uf: str
    latitude: float
    longitude: float


CIDADES: tuple[Cidade, ...] = (
    Cidade("São Paulo", "SP", -23.55, -46.63),
    Cidade("Campinas", "SP", -22.91, -47.06),
    Cidade("Ribeirão Preto", "SP", -21.18, -47.81),
    Cidade("Rio de Janeiro", "RJ", -22.91, -43.17),
    Cidade("Belo Horizonte", "MG", -19.92, -43.94),
    Cidade("Uberlândia", "MG", -18.92, -48.28),
    Cidade("Curitiba", "PR", -25.43, -49.27),
    Cidade("Londrina", "PR", -23.31, -51.16),
    Cidade("Porto Alegre", "RS", -30.03, -51.23),
    Cidade("Florianópolis", "SC", -27.60, -48.55),
    Cidade("Goiânia", "GO", -16.68, -49.25),
    Cidade("Brasília", "DF", -15.79, -47.88),
    Cidade("Salvador", "BA", -12.97, -38.50),
    Cidade("Recife", "PE", -8.05, -34.88),
    Cidade("Fortaleza", "CE", -3.73, -38.52),
    Cidade("Vitória", "ES", -20.32, -40.34),
)

PRODUTOS = (
    "Eletrônicos",
    "Autopeças",
    "Medicamentos",
    "Alimentos não perecíveis",
    "Vestuário",
    "Móveis desmontados",
    "Material de escritório",
    "Cosméticos",
)

NOMES = ("Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gabriela", "Heitor", "Iara", "João")
SOBRENOMES = ("Souza", "Lima", "Pereira", "Costa", "Almeida", "Rocha", "Barbosa", "Ribeiro")


class Gerador:
    """Produz valores fictícios determinísticos para uma mesma semente."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def uuid(self) -> uuid.UUID:
        """UUID v4 derivado do RNG (reprodutível com a mesma semente)."""
        return uuid.UUID(int=self.rng.getrandbits(128), version=4)

    def pedido_id(self) -> str:
        """Identificador `PED-` seguido de 8 dígitos hexadecimais maiúsculos."""
        return f"PED-{self.rng.getrandbits(32):08X}"

    def veiculo_id(self) -> str:
        """Identificador de veículo `VEI-NNNN`."""
        return f"VEI-{self.rng.randint(0, 9999):04d}"

    def origem_destino(self) -> tuple[Cidade, Cidade]:
        """Par de cidades distintas."""
        origem, destino = self.rng.sample(CIDADES, 2)
        return origem, destino

    def centro_distribuicao(self, cidade: Cidade) -> str:
        """Nome do centro de distribuição da cidade de origem."""
        return f"CD-{cidade.nome.upper().replace(' ', '-')}"

    def descricao(self) -> str:
        """Descrição curta do pedido."""
        return f"{self.rng.choice(PRODUTOS)} - {self.rng.randint(1, 40)} volumes"

    def peso_kg(self) -> float:
        """Peso entre 5 kg e 12 t, com uma casa decimal."""
        return round(self.rng.uniform(5, 12000), 1)

    def recebedor(self) -> str:
        """Nome fictício de quem recebeu a pedido."""
        return f"{self.rng.choice(NOMES)} {self.rng.choice(SOBRENOMES)}"

    def transitos(self) -> int:
        """Quantidade de atualizações de posição durante o trajeto (1 a 5)."""
        return self.rng.randint(1, 5)

    def sorteio(self) -> float:
        """Número uniforme em [0, 1)."""
        return self.rng.random()
