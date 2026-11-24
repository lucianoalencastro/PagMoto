from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
import secrets

db = SQLAlchemy()


class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    lojas = db.relationship('Loja', backref='dono', lazy=True)


class Loja(db.Model):
    __tablename__ = 'lojas'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    valor_encostada_padrao = db.Column(db.Numeric(10, 2), default=0.00)
    ativo = db.Column(db.Boolean, default=True)
    vencimento_assinatura = db.Column(db.Date, nullable=True)

    faixas = db.relationship('FaixaTarifa', backref='loja', lazy=True)
    motoboys = db.relationship('Motoboy', backref='loja', lazy=True)
    fechamentos = db.relationship('FechamentoDiario', backref='loja', lazy=True)


class FaixaTarifa(db.Model):
    __tablename__ = 'faixas_tarifas'
    id = db.Column(db.Integer, primary_key=True)
    loja_id = db.Column(db.Integer, db.ForeignKey('lojas.id'), nullable=False)
    descricao = db.Column(db.String(80), nullable=False)  # Ex: "0 a 4 km"
    valor = db.Column(db.Numeric(10, 2), nullable=False)  # Ex: 10.00
    ordem = db.Column(db.Integer, default=1)
    ativo = db.Column(db.Boolean, default=True)


class Motoboy(db.Model):
    __tablename__ = 'motoboys'
    id = db.Column(db.Integer, primary_key=True)
    loja_id = db.Column(db.Integer, db.ForeignKey('lojas.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(30), nullable=True)
    chave_pix = db.Column(db.String(150), nullable=True)
    token_acesso = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(24))
    ativo = db.Column(db.Boolean, default=True)

    acertos = db.relationship('AcertoMotoboy', backref='motoboy', lazy=True)



class FechamentoDiario(db.Model):
    __tablename__ = 'fechamentos_diarios'
    id = db.Column(db.Integer, primary_key=True)
    loja_id = db.Column(db.Integer, db.ForeignKey('lojas.id'), nullable=False)
    data = db.Column(db.Date, nullable=False, default=date.today)
    observacoes = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('loja_id', 'data', name='uq_loja_data'),)
    linhas = db.relationship('AcertoMotoboy', backref='fechamento', cascade='all, delete-orphan', lazy=True)
    recebimentos = db.relationship('RecebimentoDinheiro', backref='fechamento', cascade='all, delete-orphan', lazy=True)


class AcertoMotoboy(db.Model):
    __tablename__ = 'acertos_motoboys'
    id = db.Column(db.Integer, primary_key=True)
    fechamento_id = db.Column(db.Integer, db.ForeignKey('fechamentos_diarios.id'), nullable=False)
    motoboy_id = db.Column(db.Integer, db.ForeignKey('motoboys.id'), nullable=False)

    encostada = db.Column(db.Numeric(10, 2), default=0.00)
    consumo = db.Column(db.Numeric(10, 2), default=0.00)
    haver_anterior = db.Column(db.Numeric(10, 2), default=0.00)

    total_a_pagar = db.Column(db.Numeric(10, 2), default=0.00)
    valor_pago = db.Column(db.Numeric(10, 2), default=0.00)
    forma_pagamento = db.Column(db.String(50), default='Pix')
    novo_haver = db.Column(db.Numeric(10, 2), default=0.00)

    itens_faixa = db.relationship('AcertoItemFaixa', backref='acerto', cascade='all, delete-orphan', lazy=True)


class AcertoItemFaixa(db.Model):
    __tablename__ = 'acerto_itens_faixas'
    id = db.Column(db.Integer, primary_key=True)
    acerto_id = db.Column(db.Integer, db.ForeignKey('acertos_motoboys.id'), nullable=False)
    faixa_tarifa_id = db.Column(db.Integer, db.ForeignKey('faixas_tarifas.id'), nullable=True)

    descricao_snapshot = db.Column(db.String(80), nullable=False)
    valor_unitario_snapshot = db.Column(db.Numeric(10, 2), nullable=False)
    quantidade = db.Column(db.Integer, default=0)


class RecebimentoDinheiro(db.Model):
    __tablename__ = 'recebimentos_dinheiro'
    id = db.Column(db.Integer, primary_key=True)
    fechamento_id = db.Column(db.Integer, db.ForeignKey('fechamentos_diarios.id'), nullable=False)
    motoboy_id = db.Column(db.Integer, db.ForeignKey('motoboys.id'), nullable=False)
    numero_pedido = db.Column(db.String(50), nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)

    motoboy = db.relationship('Motoboy')
