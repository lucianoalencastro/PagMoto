from datetime import datetime, date
from decimal import Decimal
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, FechamentoDiario, AcertoMotoboy, AcertoItemFaixa, RecebimentoDinheiro, RascunhoRecebimentoDinheiro
from repositories import AuthRepository, FechamentoRepository, MotoboyRepository, ConfiguracaoRepository, HistoricoRepository
from helpers import parse_decimal, parse_int
from fpdf import FPDF
import re

class AuthService:
    def __init__(self):
        self.repo = AuthRepository()

    def register(self, nome: str, email: str, nome_loja: str, password: str, confirmation: str):
        if not nome or not email or not nome_loja or not password:
            return {"success": False, "message": "Preencha todos os campos obrigatórios.", "status": 400}

        if password != confirmation:
            return {"success": False, "message": "As senhas não coincidem.", "status": 400}

        if len(password) < 6:
            return {"success": False, "message": "A senha deve ter pelo menos 6 caracteres.", "status": 400}

        if self.repo.get_usuario_by_email(email):
            return {"success": False, "message": "Este e-mail já está cadastrado.", "status": 400}

        senha_hash = generate_password_hash(password)
        usuario, loja = self.repo.criar_conta_com_loja_inicial(
            nome=nome,
            email=email,
            senha_hash=senha_hash,
            nome_loja=nome_loja
        )

        return {
            "success": True,
            "user_id": usuario.id,
            "loja_id": loja.id
        }

    def login(self, email: str, password: str):
        if not email or not password:
            return {"success": False, "message": "Informe e-mail e senha.", "status": 400}

        usuario = self.repo.get_usuario_by_email(email)
        if not usuario or not check_password_hash(usuario.senha_hash, password):
            return {"success": False, "message": "E-mail ou senha inválidos.", "status": 401}

        lojas_ativas = [loja for loja in usuario.lojas if loja.ativo]
        loja_id = lojas_ativas[0].id if len(lojas_ativas) == 1 else None

        return {
            "success": True,
            "user_id": usuario.id,
            "loja_id": loja_id
        }


class FechamentoService:
    def __init__(self):
        self.repo = FechamentoRepository()

    def _to_decimal(self, valor_str) -> Decimal:
        if not valor_str:
            return Decimal("0.00")
        limpo = str(valor_str).strip().replace("R$", "").replace(" ", "").replace(",", ".")
        try:
            return Decimal(limpo).quantize(Decimal("0.01"))
        except Exception:
            return Decimal("0.00")

    def montar_planilha_dia(self, loja_id: int, data_str: str = None):
        if data_str:
            try:
                data_ref = datetime.strptime(data_str, "%Y-%m-%d").date()
            except ValueError:
                data_ref = date.today()
        else:
            data_ref = date.today()

        loja = self.repo.get_loja_com_detalhes(loja_id)
        faixas = self.repo.get_faixas_ativas(loja_id)
        motoboys = self.repo.get_motoboys_ativos(loja_id)
        fechamento = self.repo.get_fechamento_por_data(loja_id, data_ref)

        acertos_existentes = {}
        if fechamento:
            for linha in fechamento.linhas:
                qtds = {item.faixa_tarifa_id: item.quantidade for item in linha.itens_faixa}
                acertos_existentes[linha.motoboy_id] = {
                    "encostada": float(linha.encostada),
                    "extra": float(linha.extra or 0.00),
                    "consumo": float(linha.consumo),
                    "haver_anterior": float(linha.haver_anterior),
                    "total_a_pagar": float(linha.total_a_pagar),
                    "valor_pago": float(linha.valor_pago),
                    "forma_pagamento": linha.forma_pagamento,
                    "valor_pago_2": float(linha.valor_pago_2 or 0.00),
                    "forma_pagamento_2": linha.forma_pagamento_2 or "Dinheiro",
                    "novo_haver": float(linha.novo_haver),
                    "qtds": qtds
                }

        linhas_planilha = []
        for mb in motoboys:
            if mb.id in acertos_existentes:
                dados = acertos_existentes[mb.id]
            else:
                haver_ant = self.repo.get_ultimo_haver_motoboy(mb.id, data_ref)
                dados = {
                    "encostada": float(loja.valor_encostada_padrao or 0.00),
                    "extra": 0.00,
                    "consumo": 0.00,
                    "haver_anterior": haver_ant,
                    "total_a_pagar": 0.00,
                    "valor_pago": 0.00,
                    "forma_pagamento": "Pix",
                    "valor_pago_2": 0.00,
                    "forma_pagamento_2": "Dinheiro",
                    "novo_haver": haver_ant,
                    "qtds": {}
                }
            linhas_planilha.append({"motoboy": mb, **dados})

        if fechamento:
            recebimentos = fechamento.recebimentos
        else:
            recebimentos = RascunhoRecebimentoDinheiro.query.filter_by(
                loja_id=loja_id, data=data_ref
            ).order_by(RascunhoRecebimentoDinheiro.id.asc()).all()

        observacoes = fechamento.observacoes if fechamento else ""

        return {
            "data_ref": data_ref.strftime("%Y-%m-%d"),
            "data_formatada": data_ref.strftime("%d/%m/%Y"),
            "valor_encostada_padrao": float(loja.valor_encostada_padrao or 0),
            "faixas": faixas,
            "linhas": linhas_planilha,
            "recebimentos": recebimentos,
            "observacoes": observacoes,
            "ja_salvo": fechamento is not None
        }

    def sincronizar_rascunho_dinheiro(self, loja_id: int, data_str: str, itens: list):
        data_ref = datetime.strptime(data_str, "%Y-%m-%d").date()
        RascunhoRecebimentoDinheiro.query.filter_by(loja_id=loja_id, data=data_ref).delete()

        for item in itens:
            mb_id = item.get("motoboy_id")
            pedido = str(item.get("pedido", "")).strip()
            val_dec = self._to_decimal(item.get("valor"))
            if mb_id and (pedido or val_dec > 0):
                db.session.add(RascunhoRecebimentoDinheiro(
                    loja_id=loja_id,
                    data=data_ref,
                    motoboy_id=int(mb_id),
                    numero_pedido=pedido,
                    valor=val_dec
                ))
        db.session.commit()

    def salvar_fechamento(self, loja_id: int, form_data):
        data_str = form_data.get("data_fechamento")
        data_ref = datetime.strptime(data_str, "%Y-%m-%d").date()

        loja = self.repo.get_loja_com_detalhes(loja_id)
        valor_encostada_padrao = Decimal(str(loja.valor_encostada_padrao or 0))

        fechamento = self.repo.get_fechamento_por_data(loja_id, data_ref)
        if not fechamento:
            fechamento = FechamentoDiario(loja_id=loja_id, data=data_ref)
            db.session.add(fechamento)
            db.session.flush()
        else:
            fechamento.linhas.clear()
            fechamento.recebimentos.clear()
            db.session.flush()

        fechamento.observacoes = form_data.get("observacoes", "").strip()

        faixas = self.repo.get_faixas_ativas(loja_id)
        motoboys = self.repo.get_motoboys_ativos(loja_id)

        for mb in motoboys:
            prefix = f"mb_{mb.id}_"

            encostada_opcao = form_data.get(f"{prefix}encostada", "nao")
            encostada = valor_encostada_padrao if encostada_opcao == "sim" else Decimal("0.00")

            haver_anterior = Decimal(str(self.repo.get_ultimo_haver_motoboy(mb.id, data_ref)))

            extra = self._to_decimal(form_data.get(f"{prefix}extra"))
            consumo = self._to_decimal(form_data.get(f"{prefix}consumo"))
            valor_pago = self._to_decimal(form_data.get(f"{prefix}valor_pago"))
            forma_pagamento = form_data.get(f"{prefix}forma_pagamento", "Pix")
            valor_pago_2 = self._to_decimal(form_data.get(f"{prefix}valor_pago_2"))
            forma_pagamento_2 = form_data.get(f"{prefix}forma_pagamento_2") if valor_pago_2 > 0 else None

            total_entregas = Decimal("0.00")
            itens_faixa = []

            for f in faixas:
                qtd = int(form_data.get(f"{prefix}faixa_{f.id}") or 0)
                valor_unit = Decimal(str(f.valor))
                total_entregas += valor_unit * qtd

                itens_faixa.append(AcertoItemFaixa(
                    faixa_tarifa_id=f.id,
                    descricao_snapshot=f.descricao,
                    valor_unitario_snapshot=valor_unit,
                    quantidade=qtd
                ))

            total_a_pagar = total_entregas + encostada + extra + haver_anterior - consumo
            novo_haver = total_a_pagar - (valor_pago + valor_pago_2)

            acerto = AcertoMotoboy(
                fechamento_id=fechamento.id,
                motoboy_id=mb.id,
                encostada=encostada,
                extra=extra,
                consumo=consumo,
                haver_anterior=haver_anterior,
                total_a_pagar=total_a_pagar,
                valor_pago=valor_pago,
                forma_pagamento=forma_pagamento,
                valor_pago_2=valor_pago_2,
                forma_pagamento_2=forma_pagamento_2,
                novo_haver=novo_haver,
                itens_faixa=itens_faixa
            )
            db.session.add(acerto)

        rec_mbs = form_data.getlist("rec_motoboy_id[]")
        rec_pedidos = form_data.getlist("rec_pedido[]")
        rec_valores = form_data.getlist("rec_valor[]")

        for mb_id, pedido, val in zip(rec_mbs, rec_pedidos, rec_valores):
            val_dec = self._to_decimal(val)
            if mb_id and pedido.strip() and val_dec > 0:
                db.session.add(RecebimentoDinheiro(
                    fechamento_id=fechamento.id,
                    motoboy_id=int(mb_id),
                    numero_pedido=pedido.strip(),
                    valor=val_dec
                ))

        RascunhoRecebimentoDinheiro.query.filter_by(loja_id=loja_id, data=data_ref).delete()
        db.session.commit()
        return {"success": True, "data": data_str}


    def gerar_pdf_fechamento(self, loja_id: int, data_str: str = None) -> bytes:
        dados = self.montar_planilha_dia(loja_id, data_str)
        loja = self.repo.get_loja_com_detalhes(loja_id)
        faixas = dados["faixas"]
        linhas = dados["linhas"]
        recebimentos = dados["recebimentos"]

        pdf = FPDF(orientation="L", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=10)
        pdf.add_page()

        # Cabeçalho
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, f"PagMoto - Fechamento Diario ({loja.nome})", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Data de Referencia: {dados['data_formatada']}", ln=True)
        pdf.ln(3)

        # Larguras dinâmicas das colunas (Total A4 Paisagem útil = ~277mm)
        larg_nome = 38
        larg_faixa = min(18, int(90 / max(len(faixas), 1)))
        larg_enc = 20
        larg_cons = 20
        larg_hav_ant = 22
        larg_tot = 24
        larg_pago = 24
        larg_forma = 18
        larg_novo_hav = 23

        # Cabeçalho da Tabela
        pdf.set_fill_color(33, 37, 41)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 8)

        pdf.cell(larg_nome, 7, "Motoboy", border=1, fill=True)
        for f in faixas:
            pdf.cell(larg_faixa, 7, f.descricao[:10], border=1, align="C", fill=True)
        pdf.cell(larg_enc, 7, "Encost.", border=1, align="R", fill=True)
        pdf.cell(larg_cons, 7, "Consumo", border=1, align="R", fill=True)
        pdf.cell(larg_hav_ant, 7, "Haver Ant.", border=1, align="R", fill=True)
        pdf.cell(larg_tot, 7, "Total Pagar", border=1, align="R", fill=True)
        pdf.cell(larg_pago, 7, "Valor Pago", border=1, align="R", fill=True)
        pdf.cell(larg_forma, 7, "Forma", border=1, align="C", fill=True)
        pdf.cell(larg_novo_hav, 7, "Novo Haver", border=1, align="R", fill=True, ln=True)

        # Linhas dos Motoboys
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 8)

        soma_pagar = 0.0
        soma_pago = 0.0
        soma_haver = 0.0

        for item in linhas:
            mb = item["motoboy"]
            qtds = item["qtds"]
            total_entregas = sum(float(f.valor) * qtds.get(f.id, 0) for f in faixas)
            total_pagar = total_entregas + item["encostada"] + item["haver_anterior"] - item["consumo"]
            novo_haver = total_pagar - item["valor_pago"]

            soma_pagar += total_pagar
            soma_pago += item["valor_pago"]
            soma_haver += novo_haver

            pdf.cell(larg_nome, 6, mb.nome[:20], border=1)
            for f in faixas:
                pdf.cell(larg_faixa, 6, str(qtds.get(f.id, 0)), border=1, align="C")
            pdf.cell(larg_enc, 6, f"{item['encostada']:.2f}", border=1, align="R")
            pdf.cell(larg_cons, 6, f"{item['consumo']:.2f}", border=1, align="R")
            pdf.cell(larg_hav_ant, 6, f"{item['haver_anterior']:.2f}", border=1, align="R")
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(larg_tot, 6, f"{total_pagar:.2f}", border=1, align="R")
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(larg_pago, 6, f"{item['valor_pago']:.2f}", border=1, align="R")
            pdf.cell(larg_forma, 6, str(item["forma_pagamento"])[:8], border=1, align="C")
            pdf.cell(larg_novo_hav, 6, f"{novo_haver:.2f}", border=1, align="R", ln=True)

        # Rodapé de Totais
        larg_antes_totais = larg_nome + (larg_faixa * len(faixas)) + larg_enc + larg_cons + larg_hav_ant
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(larg_antes_totais, 7, "TOTAIS DO DIA (R$)", border=1, align="R", fill=True)
        pdf.cell(larg_tot, 7, f"{soma_pagar:.2f}", border=1, align="R", fill=True)
        pdf.cell(larg_pago, 7, f"{soma_pago:.2f}", border=1, align="R", fill=True)
        pdf.cell(larg_forma, 7, "-", border=1, align="C", fill=True)
        pdf.cell(larg_novo_hav, 7, f"{soma_haver:.2f}", border=1, align="R", fill=True, ln=True)

        # Recebimentos em Dinheiro e Observações
        if recebimentos:
            pdf.ln(5)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 6, "Recebimentos em Dinheiro (Pedidos):", ln=True)
            pdf.set_font("Helvetica", "", 8)
            total_din = 0.0
            for r in recebimentos:
                val = float(r.valor)
                total_din += val
                pdf.cell(0, 5, f"- {r.motoboy.nome} | Pedido: {r.numero_pedido} | R$ {val:.2f}", ln=True)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(0, 6, f"Total Dinheiro Recebido: R$ {total_din:.2f}", ln=True)

        if dados["observacoes"]:
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 6, "Observacoes:", ln=True)
            pdf.set_font("Helvetica", "", 8)
            pdf.multi_cell(0, 5, dados["observacoes"])

        return bytes(pdf.output())



class MotoboyService:
    def __init__(self):
        self.repo = MotoboyRepository()

    def listar(self, loja_id: int):
        return self.repo.listar_todos_por_loja(loja_id)

    def cadastrar(self, loja_id: int, nome: str, telefone: str, chave_pix: str):
        if not nome or not nome.strip():
            return {"success": False, "message": "O nome do motoboy é obrigatório."}
        self.repo.criar(loja_id, nome, telefone, chave_pix)
        return {"success": True, "message": "Motoboy cadastrado com sucesso!"}

    def editar(self, loja_id: int, motoboy_id: int, nome: str, telefone: str, chave_pix: str):
        motoboy = self.repo.get_by_id_e_loja(motoboy_id, loja_id)
        if not motoboy:
            return {"success": False, "message": "Motoboy não encontrado."}
        if not nome or not nome.strip():
            return {"success": False, "message": "O nome do motoboy é obrigatório."}
        self.repo.atualizar(motoboy, nome, telefone, chave_pix)
        return {"success": True, "message": "Dados atualizados com sucesso!"}

    def alternar_ativo(self, loja_id: int, motoboy_id: int):
        motoboy = self.repo.get_by_id_e_loja(motoboy_id, loja_id)
        if not motoboy:
            return {"success": False, "message": "Motoboy não encontrado."}
        self.repo.alternar_status(motoboy)
        status_txt = "ativado" if motoboy.ativo else "desativado"
        return {"success": True, "message": f"Motoboy {status_txt} com sucesso!"}

    def _normalizar_telefone(self, telefone: str) -> str:
        if not telefone:
            return None
        digitos = re.sub(r"\D", "", telefone)
        if not digitos:
            return None
        if not digitos.startswith("55") and len(digitos) in (10, 11):
            digitos = "55" + digitos
        return digitos

    def renovar_link_acesso(self, loja_id: int, motoboy_id: int):
        motoboy = self.repo.get_by_id_e_loja(motoboy_id, loja_id)
        if not motoboy:
            return {"success": False, "message": "Motoboy não encontrado."}
        self.repo.regenerar_token(motoboy)
        return {"success": True, "message": f"Novo link gerado para {motoboy.nome}! O link antigo foi bloqueado."}



class ConfiguracaoService:
    def __init__(self):
        self.repo = ConfiguracaoRepository()

    def carregar_dados(self, loja_id: int):
        loja = self.repo.get_loja(loja_id)
        faixas = self.repo.listar_faixas_por_loja(loja_id)
        return {"loja": loja, "faixas": faixas}

    def salvar_dados_loja(self, loja_id: int, nome: str, encostada_str: str):
        loja = self.repo.get_loja(loja_id)
        if not loja:
            return {"success": False, "message": "Loja não encontrada."}
        if not nome or not nome.strip():
            return {"success": False, "message": "O nome da loja é obrigatório."}

        valor_encostada = parse_decimal(encostada_str)
        if valor_encostada < Decimal("0.00"):
            return {"success": False, "message": "O valor da encostada não pode ser negativo."}

        self.repo.atualizar_loja(loja, nome, valor_encostada)
        return {"success": True, "message": "Dados da loja atualizados com sucesso!"}

    def adicionar_faixa(self, loja_id: int, descricao: str, valor_str: str, ordem_str: str):
        if not descricao or not descricao.strip():
            return {"success": False, "message": "A descrição da faixa (ex: 0 a 6 km) é obrigatória."}

        valor = parse_decimal(valor_str)
        if valor <= Decimal("0.00"):
            return {"success": False, "message": "Informe um valor válido maior que zero."}

        ordem = parse_int(ordem_str) or 1
        self.repo.criar_faixa(loja_id, descricao, valor, ordem)
        return {"success": True, "message": "Nova faixa de KM adicionada!"}

    def editar_faixa(self, loja_id: int, faixa_id: int, descricao: str, valor_str: str, ordem_str: str):
        faixa = self.repo.get_faixa_por_id_e_loja(faixa_id, loja_id)
        if not faixa:
            return {"success": False, "message": "Faixa não encontrada."}
        if not descricao or not descricao.strip():
            return {"success": False, "message": "A descrição da faixa é obrigatória."}

        valor = parse_decimal(valor_str)
        if valor <= Decimal("0.00"):
            return {"success": False, "message": "Informe um valor válido maior que zero."}

        ordem = parse_int(ordem_str) or faixa.ordem
        self.repo.atualizar_faixa(faixa, descricao, valor, ordem)
        return {"success": True, "message": "Faixa atualizada com sucesso!"}

    def alternar_faixa(self, loja_id: int, faixa_id: int):
        faixa = self.repo.get_faixa_por_id_e_loja(faixa_id, loja_id)
        if not faixa:
            return {"success": False, "message": "Faixa não encontrada."}
        self.repo.alternar_status_faixa(faixa)
        status_txt = "ativada" if faixa.ativo else "desativada"
        return {"success": True, "message": f"Faixa {status_txt} com sucesso!"}


class HistoricoService:
    def __init__(self):
        self.repo = HistoricoRepository()

    def _parse_data(self, data_str: str):
        if not data_str:
            return None
        try:
            return datetime.strptime(data_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None

    def obter_historico(self, loja_id: int, data_inicio_str: str = None, data_fim_str: str = None, motoboy_id_str: str = None):
        data_inicio = self._parse_data(data_inicio_str)
        data_fim = self._parse_data(data_fim_str)
        motoboy_id = parse_int(motoboy_id_str)

        motoboys = self.repo.listar_motoboys_loja(loja_id)
        motoboy_selecionado = None
        extrato_motoboy = []
        fechamentos_resumo = []

        total_geral_pago = Decimal("0.00")
        total_geral_haver = Decimal("0.00")
        total_geral_dinheiro = Decimal("0.00")

        # Visão 1: Extrato individual de um motoboy específico
        if motoboy_id > 0:
            motoboy_selecionado = self.repo.get_motoboy_da_loja(motoboy_id, loja_id)
            if motoboy_selecionado:
                acertos = self.repo.listar_extrato_motoboy(loja_id, motoboy_id, data_inicio, data_fim)
                for ac in acertos:
                    qtd_entregas = sum(item.quantidade for item in ac.itens_faixa)
                    extrato_motoboy.append({
                        "data": ac.fechamento.data,
                        "qtd_entregas": qtd_entregas,
                        "encostada": ac.encostada,
                        "consumo": ac.consumo,
                        "haver_anterior": ac.haver_anterior,
                        "total_a_pagar": ac.total_a_pagar,
                        "valor_pago": ac.valor_pago,
                        "forma_pagamento": ac.forma_pagamento,
                        "novo_haver": ac.novo_haver
                    })
                    total_geral_pago += Decimal(str(ac.valor_pago or 0))
                if acertos:
                    # O saldo haver atual dele é o novo_haver do fechamento mais recente
                    total_geral_haver = Decimal(str(acertos[0].novo_haver or 0))

        # Visão 2: Histórico geral por dias fechados
        else:
            fechamentos = self.repo.listar_fechamentos(loja_id, data_inicio, data_fim)
            for fech in fechamentos:
                soma_pago = sum((Decimal(str(l.valor_pago or 0)) for l in fech.linhas), Decimal("0.00"))
                soma_haver = sum((Decimal(str(l.novo_haver or 0)) for l in fech.linhas), Decimal("0.00"))
                soma_dinheiro = sum((Decimal(str(r.valor or 0)) for r in fech.recebimentos), Decimal("0.00"))
                total_entregas = sum(
                    sum(item.quantidade for item in l.itens_faixa)
                    for l in fech.linhas
                )

                fechamentos_resumo.append({
                    "id": fech.id,
                    "data": fech.data,
                    "qtd_motoboys": len(fech.linhas),
                    "total_entregas": total_entregas,
                    "total_pago": soma_pago,
                    "total_haver": soma_haver,
                    "total_dinheiro": soma_dinheiro,
                    "observacoes": fech.observacoes
                })

                total_geral_pago += soma_pago
                total_geral_haver += soma_haver
                total_geral_dinheiro += soma_dinheiro

        return {
            "motoboys": motoboys,
            "motoboy_selecionado": motoboy_selecionado,
            "extrato_motoboy": extrato_motoboy,
            "fechamentos": fechamentos_resumo,
            "filtros": {
                "data_inicio": data_inicio_str or "",
                "data_fim": data_fim_str or "",
                "motoboy_id": motoboy_id
            },
            "resumo": {
                "total_pago": total_geral_pago,
                "total_haver": total_geral_haver,
                "total_dinheiro": total_geral_dinheiro
            }
        }

    def obter_extrato_publico_motoboy(self, token: str):
        motoboy = self.repo.get_motoboy_por_token(token)
        if not motoboy:
            return None

        acertos = self.repo.listar_extrato_motoboy(motoboy.loja_id, motoboy.id)
        extrato = []
        total_pago = Decimal("0.00")

        for ac in acertos:
            qtd_entregas = sum(item.quantidade for item in ac.itens_faixa)
            valor_entregas = sum(
                (Decimal(str(item.quantidade)) * Decimal(str(item.valor_unitario_snapshot)))
                for item in ac.itens_faixa
            )
            pago_1 = Decimal(str(ac.valor_pago or 0))
            pago_2 = Decimal(str(ac.valor_pago_2 or 0))

            extrato.append({
                "data": ac.fechamento.data,
                "qtd_entregas": qtd_entregas,
                "valor_entregas": valor_entregas,
                "encostada": ac.encostada,
                "extra": ac.extra or Decimal("0.00"),
                "consumo": ac.consumo,
                "haver_anterior": ac.haver_anterior,
                "total_a_pagar": ac.total_a_pagar,
                "valor_pago": pago_1,
                "forma_pagamento": ac.forma_pagamento,
                "valor_pago_2": pago_2,
                "forma_pagamento_2": ac.forma_pagamento_2 or "",
                "novo_haver": ac.novo_haver
            })
            total_pago += pago_1 + pago_2

        saldo_haver_atual = Decimal(str(acertos[0].novo_haver or 0)) if acertos else Decimal("0.00")

        return {
            "motoboy": motoboy,
            "loja": motoboy.loja,
            "extrato": extrato,
            "saldo_haver_atual": saldo_haver_atual,
            "total_pago_acumulado": total_pago
        }
