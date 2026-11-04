"""Acesso ao banco SQLite. As consultas usam parâmetros para evitar injeção de SQL."""
import sqlite3

ESQUEMA = """
CREATE TABLE IF NOT EXISTS funcionarios (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    cargo TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS registros (
    id INTEGER PRIMARY KEY,
    funcionario_id INTEGER NOT NULL REFERENCES funcionarios(id),
    entrada TEXT NOT NULL,
    saida TEXT
);
CREATE TABLE IF NOT EXISTS atestados (
    id INTEGER PRIMARY KEY,
    funcionario_id INTEGER NOT NULL REFERENCES funcionarios(id),
    data_inicio TEXT NOT NULL,
    data_fim TEXT NOT NULL,
    observacao TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS um_registro_aberto
    ON registros(funcionario_id) WHERE saida IS NULL;
"""


def conectar(caminho):
    conexao = sqlite3.connect(caminho)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.executescript(ESQUEMA)
    return conexao


def funcionarios(conexao, somente_ativos=False):
    filtro = "WHERE ativo = 1" if somente_ativos else ""
    return conexao.execute(f"SELECT * FROM funcionarios {filtro} ORDER BY nome").fetchall()


def funcionario(conexao, funcionario_id):
    return conexao.execute("SELECT * FROM funcionarios WHERE id = ?", (funcionario_id,)).fetchone()


def registro_aberto(conexao, funcionario_id):
    return conexao.execute(
        "SELECT * FROM registros WHERE funcionario_id = ? AND saida IS NULL", (funcionario_id,)
    ).fetchone()


def ultima_saida(conexao, funcionario_id):
    return conexao.execute(
        "SELECT MAX(saida) AS saida FROM registros WHERE funcionario_id = ?", (funcionario_id,)
    ).fetchone()["saida"]


def registros_recentes(conexao, limite=20):
    return conexao.execute(
        """SELECT r.*, f.nome FROM registros r JOIN funcionarios f ON f.id = r.funcionario_id
           ORDER BY r.entrada DESC LIMIT ?""",
        (limite,),
    ).fetchall()


def atestados(conexao):
    return conexao.execute(
        """SELECT a.*, f.nome FROM atestados a JOIN funcionarios f ON f.id = a.funcionario_id
           ORDER BY a.data_inicio DESC"""
    ).fetchall()


def registros_do_mes(conexao, inicio, fim):
    return conexao.execute(
        """SELECT * FROM registros
           WHERE saida IS NOT NULL AND date(entrada) BETWEEN ? AND ?""",
        (inicio.isoformat(), fim.isoformat()),
    ).fetchall()


def atestados_do_mes(conexao, inicio, fim):
    return conexao.execute(
        "SELECT * FROM atestados WHERE data_inicio <= ? AND data_fim >= ?",
        (fim.isoformat(), inicio.isoformat()),
    ).fetchall()
