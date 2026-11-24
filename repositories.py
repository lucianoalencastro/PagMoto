from decimal import Decimal
from datetime import date, timedelta
import secrets
from models import (
    db,
    Usuario,
    Loja,
    FaixaTarifa,
    Motoboy,
    FechamentoDiario,
    AcertoMotoboy,
    RecebimentoDinheiro
)

class AuthRepository:
    def get_usuario_by_email(self, email: str):
        return Usuario.query.filter_by(email=email.strip().lower()).first()

    def criar_conta_com_loja_inicial(self, nome: str, email: str, senha_hash: str, nome_loja: str):
        novo_usuario = Usuario(
            nome=nome.strip(),
            email=email.strip().lower(),
            senha_hash=senha_hash
        )
        db.session.add(novo_usuario)
        db.session.flush()  # Gera o ID do usuário antes do commit

        # Dá 15 dias grátis de teste automático ao cadastrar
        vencimento_teste = date.today() + timedelta(days=15)

        nova_loja = Loja(
            usuario_id=novo_usuario.id,
            nome=nome_loja.strip(),
            valor_encostada_padrao=0.00,
            ativo=True,
            vencimento_assinatura=vencimento_teste
        )
        db.session.add(nova_loja)
        db.session.flush()

        # Cria 3 faixas de KM padrão para o cliente não começar com a tabela vazia
        faixas_iniciais = [
            FaixaTarifa(loja_id=nova_loja.id, descricao="0 a 4 km", valor=8.00, ordem=1),
            FaixaTarifa(loja_id=nova_loja.id, descricao="4 a 8 km", valor=10.00, ordem=2),
            FaixaTarifa(loja_id=nova_loja.id, descricao="8 a 12 km", valor=13.00, ordem=3),
        ]
        db.session.add_all(faixas_iniciais)
        db.session.commit()

        return novo_usuario, nova_loja


class FechamentoRepository:
    def get_loja_com_detalhes(self, loja_id: int):
        return Loja.query.get(loja_id)

    def get_faixas_ativas(self, loja_id: int):
        return FaixaTarifa.query.filter_by(loja_id=loja_id, ativo=True).order_by(FaixaTarifa.ordem.asc()).all()

    def get_motoboys_ativos(self, loja_id: int):
        return Motoboy.query.filter_by(loja_id=loja_id, ativo=True).order_by(Motoboy.nome.asc()).all()

    def get_fechamento_por_data(self, loja_id: int, data_ref: date):
        return FechamentoDiario.query.filter_by(loja_id=loja_id, data=data_ref).first()

    def get_ultimo_haver_motoboy(self, motoboy_id: int, data_ref: date):
        ultimo_acerto = (
            AcertoMotoboy.query
            .join(FechamentoDiario)
            .filter(
                AcertoMotoboy.motoboy_id == motoboy_id,
                FechamentoDiario.data < data_ref
            )
            .order_by(FechamentoDiario.data.desc())
            .first()
        )
        return float(ultimo_acerto.novo_haver) if ultimo_acerto else 0.00


class MotoboyRepository:
    def listar_todos_por_loja(self, loja_id: int):
        return Motoboy.query.filter_by(loja_id=loja_id).order_by(Motoboy.ativo.desc(), Motoboy.nome.asc()).all()

    def get_by_id_e_loja(self, motoboy_id: int, loja_id: int):
        return Motoboy.query.filter_by(id=motoboy_id, loja_id=loja_id).first()

    def criar(self, loja_id: int, nome: str, telefone: str, chave_pix: str):
        novo = Motoboy(
            loja_id=loja_id,
            nome=nome.strip(),
            telefone=telefone.strip() if telefone else None,
            chave_pix=chave_pix.strip() if chave_pix else None,
            ativo=True
        )
        db.session.add(novo)
        db.session.commit()
        return novo

    def atualizar(self, motoboy: Motoboy, nome: str, telefone: str, chave_pix: str):
        motoboy.nome = nome.strip()
        motoboy.telefone = telefone.strip() if telefone else None
        motoboy.chave_pix = chave_pix.strip() if chave_pix else None
        db.session.commit()

    def alternar_status(self, motoboy: Motoboy):
        motoboy.ativo = not motoboy.ativo
        db.session.commit()

    def regenerar_token(self, motoboy: Motoboy):
        motoboy.token_acesso = secrets.token_urlsafe(24)
        db.session.commit()
        return motoboy.token_acesso


class ConfiguracaoRepository:
    def get_loja(self, loja_id: int):
        return Loja.query.get(loja_id)

    def atualizar_loja(self, loja: Loja, nome: str, valor_encostada: Decimal):
        loja.nome = nome.strip()
        loja.valor_encostada_padrao = valor_encostada
        db.session.commit()

    def listar_faixas_por_loja(self, loja_id: int):
        return FaixaTarifa.query.filter_by(loja_id=loja_id).order_by(FaixaTarifa.ativo.desc(), FaixaTarifa.ordem.asc(), FaixaTarifa.id.asc()).all()

    def get_faixa_por_id_e_loja(self, faixa_id: int, loja_id: int):
        return FaixaTarifa.query.filter_by(id=faixa_id, loja_id=loja_id).first()

    def criar_faixa(self, loja_id: int, descricao: str, valor: Decimal, ordem: int):
        nova = FaixaTarifa(
            loja_id=loja_id,
            descricao=descricao.strip(),
            valor=valor,
            ordem=ordem,
            ativo=True
        )
        db.session.add(nova)
        db.session.commit()
        return nova

    def atualizar_faixa(self, faixa: FaixaTarifa, descricao: str, valor: Decimal, ordem: int):
        faixa.descricao = descricao.strip()
        faixa.valor = valor
        faixa.ordem = ordem
        db.session.commit()

    def alternar_status_faixa(self, faixa: FaixaTarifa):
        faixa.ativo = not faixa.ativo
        db.session.commit()


class HistoricoRepository:
    def listar_fechamentos(self, loja_id: int, data_inicio: date = None, data_fim: date = None):
        query = FechamentoDiario.query.filter_by(loja_id=loja_id)
        if data_inicio:
            query = query.filter(FechamentoDiario.data >= data_inicio)
        if data_fim:
            query = query.filter(FechamentoDiario.data <= data_fim)
        return query.order_by(FechamentoDiario.data.desc()).all()

    def listar_extrato_motoboy(self, loja_id: int, motoboy_id: int, data_inicio: date = None, data_fim: date = None):
        query = (
            AcertoMotoboy.query
            .join(FechamentoDiario)
            .filter(
                FechamentoDiario.loja_id == loja_id,
                AcertoMotoboy.motoboy_id == motoboy_id
            )
        )
        if data_inicio:
            query = query.filter(FechamentoDiario.data >= data_inicio)
        if data_fim:
            query = query.filter(FechamentoDiario.data <= data_fim)
        return query.order_by(FechamentoDiario.data.desc()).all()

    def get_motoboy_da_loja(self, motoboy_id: int, loja_id: int):
        return Motoboy.query.filter_by(id=motoboy_id, loja_id=loja_id).first()

    def listar_motoboys_loja(self, loja_id: int):
        return Motoboy.query.filter_by(loja_id=loja_id).order_by(Motoboy.nome.asc()).all()

    def get_motoboy_por_token(self, token: str):
        if not token:
            return None
        return Motoboy.query.filter_by(token_acesso=token.strip(), ativo=True).first()


