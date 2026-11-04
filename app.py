"""Aplicação web do controle de ponto."""
import csv
import io
import os
import secrets
from datetime import date, datetime
from pathlib import Path

from flask import Flask, Response, flash, g, redirect, render_template, request, url_for

import banco
import regras
from regras import ErroDeRegra

CAMINHO_PADRAO = Path(__file__).with_name("ponto.db")
DESTINOS_DE_ERRO = {
    "registrar_entrada": "ponto",
    "registrar_saida": "ponto",
    "alternar_situacao": "funcionarios",
    "relatorio": "ponto",
    "relatorio_csv": "ponto",
}


def criar_app(caminho_banco=CAMINHO_PADRAO):
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    def db():
        if "db" not in g:
            g.db = banco.conectar(caminho_banco)
        return g.db

    @app.teardown_appcontext
    def fechar_banco(_erro):
        conexao = g.pop("db", None)
        if conexao:
            conexao.close()

    @app.errorhandler(ErroDeRegra)
    def mostrar_erro(erro):
        flash(str(erro), "erro")
        destino = DESTINOS_DE_ERRO.get(request.endpoint, request.endpoint)
        argumentos = request.view_args if destino == "editar_funcionario" else {}
        return redirect(url_for(destino, **argumentos))

    @app.template_filter("data_hora")
    def data_hora(texto):
        return datetime.fromisoformat(texto).strftime("%d/%m/%Y %H:%M") if texto else "-"

    @app.template_filter("data")
    def data_br(texto):
        return date.fromisoformat(texto).strftime("%d/%m/%Y")

    def funcionario_do_formulario():
        pessoa = banco.funcionario(db(), request.form.get("funcionario_id", type=int))
        if not pessoa or not pessoa["ativo"]:
            raise ErroDeRegra("Selecione um funcionário ativo.")
        return pessoa

    def dados_do_funcionario():
        nome = request.form.get("nome", "").strip()
        cargo = request.form.get("cargo", "").strip()
        if not nome or not cargo:
            raise ErroDeRegra("Informe o nome e o cargo.")
        return nome, cargo

    @app.get("/")
    def ponto():
        pessoas = [
            {"dados": pessoa, "aberto": banco.registro_aberto(db(), pessoa["id"])}
            for pessoa in banco.funcionarios(db(), somente_ativos=True)
        ]
        agora = datetime.now().strftime("%Y-%m-%dT%H:%M")
        return render_template("ponto.html", pessoas=pessoas, agora=agora,
                               registros=banco.registros_recentes(db()))

    @app.post("/ponto/entrada")
    def registrar_entrada():
        pessoa = funcionario_do_formulario()
        momento = regras.ler_data_hora(request.form.get("momento"))
        anterior = banco.ultima_saida(db(), pessoa["id"])
        regras.validar_entrada(
            banco.registro_aberto(db(), pessoa["id"]), momento,
            regras.ler_data_hora(anterior) if anterior else None,
        )
        db().execute("INSERT INTO registros (funcionario_id, entrada) VALUES (?, ?)",
                     (pessoa["id"], momento.isoformat()))
        db().commit()
        flash(f"Entrada de {pessoa['nome']} registrada.")
        return redirect(url_for("ponto"))

    @app.post("/ponto/saida")
    def registrar_saida():
        pessoa = funcionario_do_formulario()
        momento = regras.ler_data_hora(request.form.get("momento"))
        aberto = banco.registro_aberto(db(), pessoa["id"])
        regras.validar_saida(aberto, momento)
        db().execute("UPDATE registros SET saida = ? WHERE id = ?", (momento.isoformat(), aberto["id"]))
        db().commit()
        flash(f"Saída de {pessoa['nome']} registrada.")
        return redirect(url_for("ponto"))

    @app.route("/funcionarios", methods=["GET", "POST"])
    def funcionarios():
        if request.method == "POST":
            nome, cargo = dados_do_funcionario()
            db().execute("INSERT INTO funcionarios (nome, cargo) VALUES (?, ?)", (nome, cargo))
            db().commit()
            flash("Funcionário cadastrado.")
            return redirect(url_for("funcionarios"))
        return render_template("funcionarios.html", pessoas=banco.funcionarios(db()))

    @app.route("/funcionarios/<int:funcionario_id>/editar", methods=["GET", "POST"])
    def editar_funcionario(funcionario_id):
        pessoa = banco.funcionario(db(), funcionario_id)
        if not pessoa:
            return "Funcionário não encontrado.", 404
        if request.method == "POST":
            nome, cargo = dados_do_funcionario()
            db().execute("UPDATE funcionarios SET nome = ?, cargo = ? WHERE id = ?",
                         (nome, cargo, funcionario_id))
            db().commit()
            flash("Funcionário atualizado.")
            return redirect(url_for("funcionarios"))
        return render_template("editar_funcionario.html", pessoa=pessoa)

    @app.post("/funcionarios/<int:funcionario_id>/situacao")
    def alternar_situacao(funcionario_id):
        pessoa = banco.funcionario(db(), funcionario_id)
        if not pessoa:
            return "Funcionário não encontrado.", 404
        if pessoa["ativo"] and banco.registro_aberto(db(), funcionario_id):
            raise ErroDeRegra("Registre a saída antes de desativar este funcionário.")
        db().execute("UPDATE funcionarios SET ativo = ? WHERE id = ?",
                     (0 if pessoa["ativo"] else 1, funcionario_id))
        db().commit()
        flash("Situação atualizada.")
        return redirect(url_for("funcionarios"))

    @app.route("/atestados", methods=["GET", "POST"])
    def atestados():
        if request.method == "POST":
            pessoa = funcionario_do_formulario()
            inicio = regras.ler_data(request.form.get("data_inicio"))
            fim = regras.ler_data(request.form.get("data_fim"))
            regras.validar_atestado(inicio, fim)
            db().execute(
                "INSERT INTO atestados (funcionario_id, data_inicio, data_fim, observacao) VALUES (?, ?, ?, ?)",
                (pessoa["id"], inicio.isoformat(), fim.isoformat(), request.form.get("observacao", "").strip()),
            )
            db().commit()
            flash("Atestado registrado.")
            return redirect(url_for("atestados"))
        return render_template("atestados.html", atestados=banco.atestados(db()),
                               pessoas=banco.funcionarios(db(), somente_ativos=True))

    def montar_relatorio(mes):
        inicio, fim = regras.limites_do_mes(mes)
        linhas = {
            pessoa["id"]: {"nome": pessoa["nome"], "cargo": pessoa["cargo"], "minutos": 0, "dias": set(), "atestado": 0}
            for pessoa in banco.funcionarios(db())
        }
        for registro in banco.registros_do_mes(db(), inicio, fim):
            entrada = regras.ler_data_hora(registro["entrada"])
            linha = linhas[registro["funcionario_id"]]
            linha["minutos"] += regras.minutos_trabalhados(entrada, regras.ler_data_hora(registro["saida"]))
            linha["dias"].add(entrada.date())
        for atestado in banco.atestados_do_mes(db(), inicio, fim):
            linhas[atestado["funcionario_id"]]["atestado"] += regras.dias_no_periodo(
                regras.ler_data(atestado["data_inicio"]), regras.ler_data(atestado["data_fim"]), inicio, fim
            )
        return [
            {**linha, "dias": len(linha["dias"]), "horas": regras.formatar_minutos(linha["minutos"])}
            for linha in linhas.values()
        ]

    @app.get("/relatorio")
    def relatorio():
        mes = request.args.get("mes") or date.today().strftime("%Y-%m")
        return render_template("relatorio.html", mes=mes, linhas=montar_relatorio(mes))

    @app.get("/relatorio.csv")
    def relatorio_csv():
        mes = request.args.get("mes") or date.today().strftime("%Y-%m")
        linhas = montar_relatorio(mes)
        saida = io.StringIO()
        escritor = csv.writer(saida, delimiter=";")
        escritor.writerow(["Funcionário", "Cargo", "Horas", "Dias trabalhados", "Dias de atestado"])
        for linha in linhas:
            escritor.writerow([linha["nome"], linha["cargo"], linha["horas"], linha["dias"], linha["atestado"]])
        return Response(
            "﻿" + saida.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=relatorio-{mes}.csv"},
        )

    return app


if __name__ == "__main__":
    criar_app().run(host="127.0.0.1", port=5000)
