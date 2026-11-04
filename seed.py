"""Preenche o banco com dados fictícios. Rode uma vez com: python seed.py"""
from datetime import date, datetime, time, timedelta

import banco
from app import CAMINHO_PADRAO

PESSOAS = [
    ("Ana Exemplo", "Auxiliar Administrativa"),
    ("Bruno Fictício", "Vendedor"),
    ("Carla Modelo", "Recepcionista"),
]


def preencher(caminho=CAMINHO_PADRAO):
    conexao = banco.conectar(caminho)
    if banco.funcionarios(conexao):
        print("O banco já tem dados. Nada foi alterado.")
        return
    ids = [
        conexao.execute("INSERT INTO funcionarios (nome, cargo) VALUES (?, ?)", pessoa).lastrowid
        for pessoa in PESSOAS
    ]
    hoje = date.today()
    for dias_atras in range(30, 0, -1):
        dia = hoje - timedelta(days=dias_atras)
        if dia.weekday() >= 5:
            continue
        for posicao, funcionario_id in enumerate(ids):
            entrada = datetime.combine(dia, time(8, 0)) + timedelta(minutes=5 * posicao)
            saida = entrada + timedelta(hours=8, minutes=(dias_atras + posicao) % 4 * 10)
            conexao.execute(
                "INSERT INTO registros (funcionario_id, entrada, saida) VALUES (?, ?, ?)",
                (funcionario_id, entrada.isoformat(), saida.isoformat()),
            )
    inicio = hoje - timedelta(days=12)
    conexao.execute(
        "INSERT INTO atestados (funcionario_id, data_inicio, data_fim, observacao) VALUES (?, ?, ?, ?)",
        (ids[1], inicio.isoformat(), (inicio + timedelta(days=1)).isoformat(), "Atestado fictício"),
    )
    conexao.commit()
    conexao.close()
    print("Dados fictícios criados.")


if __name__ == "__main__":
    preencher()
