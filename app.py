import os
from flask import Flask, flash, redirect, render_template, request, session, Response
from models import db, Usuario, Loja
from helpers import login_required, loja_required
from services import AuthService, FechamentoService, MotoboyService, ConfiguracaoService, HistoricoService

auth_service = AuthService()
fechamento_service = FechamentoService()
motoboy_service = MotoboyService()
config_service = ConfiguracaoService()
historico_service = HistoricoService()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "chave-secreta-dev-pagmoto")
app.config["SESSION_PERMANENT"] = False

database_url = os.getenv("DATABASE_URL", "sqlite:///pagmoto.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

if database_url.startswith("postgresql://"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "connect_args": {"sslmode": "require"},
    }

db.init_app(app)

with app.app_context():
    db.create_all()


@app.after_request
def after_request(response):
    if not request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
    return response


@app.context_processor
def inject_global_data():
    usuario = None
    loja_atual = None
    minhas_lojas = []

    if 'user_id' in session:
        usuario = Usuario.query.get(session['user_id'])
        if usuario:
            minhas_lojas = [loja for loja in usuario.lojas if loja.ativo]

    if 'loja_id' in session:
        loja_atual = Loja.query.get(session['loja_id'])

    return dict(
        usuario_atual=usuario,
        loja_atual=loja_atual,
        minhas_lojas=minhas_lojas
    )


@app.route("/", methods=["GET", "POST"])
@loja_required
def index():
    loja_id = session["loja_id"]

    if request.method == "POST":
        result = fechamento_service.salvar_fechamento(loja_id, request.form)
        flash("Fechamento salvo com sucesso!", "success")
        return redirect(f"/?data={result['data']}")

    data_query = request.args.get("data")
    dados = fechamento_service.montar_planilha_dia(loja_id, data_query)
    return render_template("index.html", **dados)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        result = auth_service.register(
            nome=request.form.get("nome"),
            email=request.form.get("email"),
            nome_loja=request.form.get("nome_loja"),
            password=request.form.get("password"),
            confirmation=request.form.get("confirmation")
        )
        if not result["success"]:
            return result["message"], result["status"]

        session["user_id"] = result["user_id"]
        session["loja_id"] = result["loja_id"]
        return redirect("/")

    return render_template("auth/register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    session.clear()

    if request.method == "POST":
        result = auth_service.login(
            email=request.form.get("email"),
            password=request.form.get("password")
        )
        if not result["success"]:
            return result["message"], result["status"]

        session["user_id"] = result["user_id"]
        
        # Se o usuário já tiver uma loja vinculada, já define na sessão para abrir direto
        if result.get("loja_id"):
            session["loja_id"] = result["loja_id"]
            return redirect("/")

        # Caso tenha mais de uma loja (ou nenhuma), manda para a seleção de lojas
        return redirect("/selecionar-loja")

    return render_template("auth/login.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect("/login")


@app.route("/motoboys", methods=["GET", "POST"])
@loja_required
def motoboys():
    loja_id = session["loja_id"]

    if request.method == "POST":
        res = motoboy_service.cadastrar(
            loja_id=loja_id,
            nome=request.form.get("nome"),
            telefone=request.form.get("telefone"),
            chave_pix=request.form.get("chave_pix")
        )
        flash(res["message"], "success" if res["success"] else "danger")
        return redirect("/motoboys")

    lista = motoboy_service.listar(loja_id)
    return render_template("motoboys.html", motoboys=lista)


@app.route("/motoboys/<int:motoboy_id>/editar", methods=["POST"])
@loja_required
def editar_motoboy(motoboy_id):
    res = motoboy_service.editar(
        loja_id=session["loja_id"],
        motoboy_id=motoboy_id,
        nome=request.form.get("nome"),
        telefone=request.form.get("telefone"),
        chave_pix=request.form.get("chave_pix")
    )
    flash(res["message"], "success" if res["success"] else "danger")
    return redirect("/motoboys")


@app.route("/motoboys/<int:motoboy_id>/toggle", methods=["POST"])
@loja_required
def toggle_motoboy(motoboy_id):
    res = motoboy_service.alternar_ativo(session["loja_id"], motoboy_id)
    flash(res["message"], "success" if res["success"] else "danger")
    return redirect("/motoboys")


@app.route("/motoboys/<int:motoboy_id>/novo-link", methods=["post"])
@loja_required
def novo_link_motoboy(motoboy_id):
    res = motoboy_service.renovar_link_acesso(session["loja_id"], motoboy_id)
    flash(res["message"], "success" if res["success"] else "danger")
    return redirect("/motoboys")


@app.route("/extrato/<string:token>", methods=["get"])
def app_motoboy(token):
    dados = historico_service.obter_extrato_publico_motoboy(token)
    if not dados:
        return render_template("bloqueado.html"), 404
    return render_template("app_motoboy.html", **dados)



@app.route("/bloqueado")
def bloqueado():
    return render_template("bloqueado.html")


@app.route("/configuracoes", methods=["GET"])
@loja_required
def configuracoes():
    dados = config_service.carregar_dados(session["loja_id"])
    return render_template("configuracoes.html", **dados)


@app.route("/configuracoes/loja", methods=["POST"])
@loja_required
def atualizar_loja():
    res = config_service.salvar_dados_loja(
        loja_id=session["loja_id"],
        nome=request.form.get("nome"),
        encostada_str=request.form.get("valor_encostada_padrao")
    )
    flash(res["message"], "success" if res["success"] else "danger")
    return redirect("/configuracoes")


@app.route("/configuracoes/faixas", methods=["POST"])
@loja_required
def adicionar_faixa():
    res = config_service.adicionar_faixa(
        loja_id=session["loja_id"],
        descricao=request.form.get("descricao"),
        valor_str=request.form.get("valor"),
        ordem_str=request.form.get("ordem")
    )
    flash(res["message"], "success" if res["success"] else "danger")
    return redirect("/configuracoes")


@app.route("/configuracoes/faixas/<int:faixa_id>/editar", methods=["POST"])
@loja_required
def editar_faixa(faixa_id):
    res = config_service.editar_faixa(
        loja_id=session["loja_id"],
        faixa_id=faixa_id,
        descricao=request.form.get("descricao"),
        valor_str=request.form.get("valor"),
        ordem_str=request.form.get("ordem")
    )
    flash(res["message"], "success" if res["success"] else "danger")
    return redirect("/configuracoes")


@app.route("/configuracoes/faixas/<int:faixa_id>/toggle", methods=["POST"])
@loja_required
def toggle_faixa(faixa_id):
    res = config_service.alternar_faixa(session["loja_id"], faixa_id)
    flash(res["message"], "success" if res["success"] else "danger")
    return redirect("/configuracoes")


@app.route("/historico", methods=["GET"])
@loja_required
def historico():
    dados = historico_service.obter_historico(
        loja_id=session["loja_id"],
        data_inicio_str=request.args.get("data_inicio"),
        data_fim_str=request.args.get("data_fim"),
        motoboy_id_str=request.args.get("motoboy_id")
    )
    return render_template("historico.html", **dados)


@app.route("/fechamento/pdf", methods=["get"])
@loja_required
def baixar_pdf_fechamento():
    data_query = request.args.get("data")
    pdf_bytes = fechamento_service.gerar_pdf_fechamento(session["loja_id"], data_query)
    nome_arquivo = f"fechamento_{data_query or 'hoje'}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )


if __name__ == "__main__":
    app.run(debug=True)