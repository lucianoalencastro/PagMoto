from functools import wraps
from datetime import date, timedelta
from flask import redirect, session
from models import Loja
from decimal import Decimal, InvalidOperation


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


def loja_required(f):
    """
    Garante que o usuário está logado, tem uma loja selecionada
    e a assinatura da loja está ativa/em dia.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")

        loja_id = session.get("loja_id")
        if loja_id is None:
            return redirect("/selecionar-loja")

        loja = Loja.query.get(loja_id)
        if not loja or not loja.ativo:
            return redirect("/bloqueado")

        if loja.vencimento_assinatura:
            limite = loja.vencimento_assinatura + timedelta(days=5)
            if date.today() > limite:
                return redirect("/bloqueado")

        return f(*args, **kwargs)

    return decorated_function


def parse_decimal(valor_str) -> Decimal:
    """Converte strings como '12,50', '12.50' ou '' em Decimal seguro."""
    if valor_str is None:
        return Decimal("0.00")
    texto = str(valor_str).strip().replace("R$", "").replace(" ", "")
    if not texto:
        return Decimal("0.00")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return Decimal("0.00")


def parse_int(valor_str) -> int:
    """Converte strings numéricas ou vazias em inteiro seguro."""
    if valor_str is None:
        return 0
    try:
        return int(str(valor_str).strip())
    except (ValueError, TypeError):
        return 0

