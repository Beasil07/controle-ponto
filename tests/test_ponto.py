import sqlite3
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import banco
import regras
from app import criar_app
from regras import ErroDeRegra


class RegrasTest(unittest.TestCase):
    def test_calcula_minutos_e_formata(self):
        minutos = regras.minutos_trabalhados(datetime(2026, 1, 5, 8, 0), datetime(2026, 1, 5, 17, 35))
        self.assertEqual(minutos, 575)
        self.assertEqual(regras.formatar_minutos(minutos), "09:35")

    def test_calcula_turno_que_passa_da_meia_noite(self):
        minutos = regras.minutos_trabalhados(datetime(2026, 1, 5, 22, 0), datetime(2026, 1, 6, 6, 0))
        self.assertEqual(minutos, 480)

    def test_bloqueia_segunda_entrada(self):
        with self.assertRaises(ErroDeRegra):
            regras.validar_entrada({"entrada": "2026-01-05T08:00:00"}, datetime(2026, 1, 5, 9, 0))

    def test_bloqueia_entrada_antes_da_ultima_saida(self):
        with self.assertRaises(ErroDeRegra):
            regras.validar_entrada(None, datetime(2026, 1, 5, 9, 0), datetime(2026, 1, 5, 10, 0))

    def test_bloqueia_saida_sem_entrada(self):
        with self.assertRaises(ErroDeRegra):
            regras.validar_saida(None, datetime(2026, 1, 5, 17, 0))

    def test_bloqueia_saida_antes_da_entrada(self):
        with self.assertRaises(ErroDeRegra):
            regras.validar_saida({"entrada": "2026-01-05T08:00:00"}, datetime(2026, 1, 5, 8, 0))

    def test_limites_do_mes(self):
        self.assertEqual(regras.limites_do_mes("2028-02"), (date(2028, 2, 1), date(2028, 2, 29)))
        self.assertEqual(regras.limites_do_mes("2026-12"), (date(2026, 12, 1), date(2026, 12, 31)))
        with self.assertRaises(ErroDeRegra):
            regras.limites_do_mes("2026-13")

    def test_atestado_entre_dois_meses(self):
        inicio, fim = regras.limites_do_mes("2026-02")
        self.assertEqual(regras.dias_no_periodo(date(2026, 1, 30), date(2026, 2, 2), inicio, fim), 2)
        self.assertEqual(regras.dias_no_periodo(date(2026, 3, 1), date(2026, 3, 2), inicio, fim), 0)

    def test_atestado_com_datas_invertidas(self):
        with self.assertRaises(ErroDeRegra):
            regras.validar_atestado(date(2026, 1, 5), date(2026, 1, 4))


class SistemaTest(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.caminho = Path(self.pasta.name) / "teste.db"
        self.cliente = criar_app(self.caminho).test_client()
        self.cliente.post("/funcionarios", data={"nome": "Ana Exemplo", "cargo": "Auxiliar"})

    def tearDown(self):
        self.pasta.cleanup()

    def enviar(self, rota, **dados):
        return self.cliente.post(rota, data=dados, follow_redirects=True).get_data(as_text=True)

    def test_fluxo_completo_e_csv(self):
        self.enviar("/ponto/entrada", funcionario_id=1, momento="2026-03-02T08:00")
        self.enviar("/ponto/saida", funcionario_id=1, momento="2026-03-02T17:30")
        self.enviar("/atestados", funcionario_id=1, data_inicio="2026-03-03", data_fim="2026-03-04", observacao="")

        pagina = self.cliente.get("/relatorio?mes=2026-03").get_data(as_text=True)
        self.assertIn("09:30", pagina)
        csv = self.cliente.get("/relatorio.csv?mes=2026-03").get_data(as_text=True)
        self.assertIn("Ana Exemplo;Auxiliar;09:30;1;2", csv)

    def test_saida_sem_entrada_mostra_erro(self):
        pagina = self.enviar("/ponto/saida", funcionario_id=1, momento="2026-03-02T17:30")
        self.assertIn("Não existe entrada aberta", pagina)

    def test_nao_desativa_com_entrada_aberta(self):
        self.enviar("/ponto/entrada", funcionario_id=1, momento="2026-03-02T08:00")
        pagina = self.enviar("/funcionarios/1/situacao")
        self.assertIn("Registre a saída", pagina)

    def test_funcionario_inativo_nao_registra_ponto(self):
        self.enviar("/funcionarios/1/situacao")
        pagina = self.enviar("/ponto/entrada", funcionario_id=1, momento="2026-03-02T08:00")
        self.assertIn("Selecione um funcionário ativo", pagina)

    def test_edita_funcionario_e_escapa_html(self):
        pagina = self.enviar("/funcionarios/1/editar", nome="<b>Ana</b>", cargo="Gerente")
        self.assertIn("&lt;b&gt;Ana&lt;/b&gt;", pagina)
        self.assertEqual(self.cliente.get("/funcionarios/99/editar").status_code, 404)

    def test_edicao_invalida_volta_para_o_formulario(self):
        pagina = self.enviar("/funcionarios/1/editar", nome="", cargo="")
        self.assertIn("Informe o nome e o cargo", pagina)
        self.assertIn("Editar funcionário", pagina)

    def test_mes_invalido_nao_quebra(self):
        resposta = self.cliente.get("/relatorio?mes=abc", follow_redirects=True)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Informe um mês válido", resposta.get_data(as_text=True))

    def test_banco_impede_dois_registros_abertos(self):
        conexao = banco.conectar(self.caminho)
        conexao.execute("INSERT INTO registros (funcionario_id, entrada) VALUES (1, '2026-03-02T08:00')")
        with self.assertRaises(sqlite3.IntegrityError):
            conexao.execute("INSERT INTO registros (funcionario_id, entrada) VALUES (1, '2026-03-02T09:00')")
        conexao.close()


if __name__ == "__main__":
    unittest.main()
