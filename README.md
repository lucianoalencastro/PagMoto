# PagMoto - Sistema de Fechamento e Pagamento de Motoboys

Sistema web completo desenvolvido em **Python (Flask + SQLAlchemy)** para gestão diária de entregas, diárias (encostadas), consumo interno, controle de saldo acumulado (haver), recebimentos em dinheiro e extrato mobile exclusivo para entregadores.

## Funcionalidades Principais

- **Planilha de Fechamento Diário:**
  - Cálculo automático por faixas de entrega configuráveis por loja.
  - Seleção rápida de diária/encostada (**Sim / Não**) com valor padrão da loja.
  - Controle automático e bloqueado de **Haver Anterior** e **Novo Haver** (saldo acumulado entre turnos).
  - Desconto de consumo/vales e registro de forma de pagamento (Pix, Dinheiro, Deixar Haver).
  - Controle de pedidos recebidos em dinheiro pelos entregadores.
- **Exportação em PDF:** Geração direta de relatório diário em A4 Paisagem (`fpdf2`).
- **App / Extrato Exclusivo do Motoboy:**
  - Link único com token seguro (`/extrato/<token>`) para consulta pelo celular, sem necessidade de senha.
  - Compartilhamento direto via WhatsApp com 1 clique.
- **Multi-loja & Histórico:** Gestão de motoboys, faixas de tarifa, histórico de fechamentos passados e cadastro de lojas.

## Tecnologias Utilizadas

- **Backend:** Python 3, Flask, Flask-SQLAlchemy, Werkzeug Security
- **Frontend:** HTML5, Bootstrap 5.3, JavaScript Vanilla
- **Relatórios:** FPDF2
- **Banco de Dados:** SQLite (desenvolvimento) / PostgreSQL (produção)

## Como Rodar Localmente

```bash
# 1. Clone o repositório
git clone https://github.com
cd PagMoto

# 2. Crie e ative o ambiente virtual
python -m venv venv
venv\Scripts\activate  # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Inicie o servidor
flask --debug run
```