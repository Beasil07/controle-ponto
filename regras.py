"""Regras de negócio do controle de ponto, separadas do banco e da tela."""
from datetime import date, datetime, timedelta


class ErroDeRegra(Exception):
    """Erro de validação que pode ser mostrado para quem usa o sistema."""


def ler_data_hora(texto):
    try:
        return datetime.fromisoformat(texto)
    except (TypeError, ValueError):
        raise ErroDeRegra("Informe uma data e hora válidas.") from None


def ler_data(texto):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        raise ErroDeRegra("Informe uma data válida.") from None


def validar_entrada(registro_aberto, entrada, ultima_saida=None):
    if registro_aberto:
        raise ErroDeRegra("Este funcionário já tem uma entrada aberta.")
    if ultima_saida and entrada < ultima_saida:
        raise ErroDeRegra("A entrada não pode ser anterior à última saída.")


def validar_saida(registro_aberto, saida):
    if not registro_aberto:
        raise ErroDeRegra("Não existe entrada aberta para este funcionário.")
    if saida <= ler_data_hora(registro_aberto["entrada"]):
        raise ErroDeRegra("A saída precisa ser depois da entrada.")


def validar_atestado(inicio, fim):
    if fim < inicio:
        raise ErroDeRegra("A data final não pode ser anterior à data inicial.")


def minutos_trabalhados(entrada, saida):
    return int((saida - entrada).total_seconds() // 60)


def formatar_minutos(minutos):
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def limites_do_mes(mes):
    try:
        inicio = datetime.strptime(mes, "%Y-%m").date()
    except (TypeError, ValueError):
        raise ErroDeRegra("Informe um mês válido.") from None
    proximo = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
    return inicio, proximo - timedelta(days=1)


def dias_no_periodo(inicio, fim, periodo_inicio, periodo_fim):
    """Conta quantos dias de um atestado caem dentro do período."""
    comeco = max(inicio, periodo_inicio)
    final = min(fim, periodo_fim)
    return max((final - comeco).days + 1, 0)
