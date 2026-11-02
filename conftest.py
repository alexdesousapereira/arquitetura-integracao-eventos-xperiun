"""Configuração global do pytest.

Os diretórios dos membros do workspace têm o mesmo nome dos pacotes (`contratos/`,
`simulador/`...). No modo `--import-mode=importlib`, o pytest cria módulos sintéticos a partir do
caminho dos testes (ex.: `contratos.tests.unit.test_evento`), o que registraria o diretório como
um namespace package e esconderia o pacote real. Importar os pacotes reais antes da coleta evita
esse conflito.
"""

import api_consulta  # noqa: F401
import contratos  # noqa: F401
import controle_ingestao  # noqa: F401
import simulador  # noqa: F401
