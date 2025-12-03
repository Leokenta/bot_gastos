import logging
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
import openpyxl
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

# ----------------------
# Arquivo de dados JSON
# ----------------------
DATA_FILE = "gastos.json"
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"gastos": []}, f)

def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ----------------------
# Estados do usuário
# ----------------------
user_state = {}

# Categorias
CATEGORIAS = {
    "mercado": "🛒 Mercado",
    "virtual": "💳 Gasto Virtual",
    "diversao": "🎉 Diversão",
    "posto": "⛽ Posto de Gasolina",
    "fixo": "💼 Gasto Fixo",
    "compras": "🛍️ Compras",
    "comidinhas": "🍔 Comidinhas"
}

# ----------------------
# Atualização de parcelas
# ----------------------
def atualizar_parcelas():
    data = load_data()
    hoje = datetime.now()
    mes_atual = f"{hoje.year}-{hoje.month}"

    for gasto in data["gastos"]:
        if gasto.get("categoria") in ["virtual", "compras"] and gasto.get("ultimo_update") != mes_atual:
            gasto["parcelas_restantes"] -= 1
            gasto["ultimo_update"] = mes_atual

    data["gastos"] = [
        g for g in data["gastos"]
        if (
            g.get("categoria") == "fixo"
            or g.get("categoria") in ["virtual", "compras"]
            or g.get("parcelas_restantes", 1) > 0
        )
    ]

    save_data(data)

# ----------------------
# Planilha Excel
# ----------------------
def gerar_planilha():
    data = load_data()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Gastos"

    ws.append(["Quem Gastou", "Produto", "Categoria", "Valor Total", "Parcela Valor", "Parcelas Restantes", "Data"])

    for gasto in data["gastos"]:
        ws.append([
            gasto.get("quem", "—"),
            gasto.get("produto", ""),
            gasto["categoria"],
            gasto.get("valor_total", gasto.get("valor", 0)),
            gasto.get("parcela_valor", ""),
            gasto.get("parcelas_restantes", ""),
            gasto.get("ultimo_update", gasto.get("data", ""))
        ])

    caminho = "resumo_gastos.xlsx"
    wb.save(caminho)
    return caminho

# ----------------------
# Comandos Telegram
# ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    atualizar_parcelas()
    await update.message.reply_text(
        "Olá! Digite um valor para registrar um gasto, ou use (ajuda) para ver os comandos."
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    estado = user_state.get(user_id)
    data = load_data()

    # Seleção de quem gastou
    if query.data in ["quem_lissa", "quem_leonardo", "quem_nosso"]:
        quem = {"quem_lissa": "Lissa", "quem_leonardo": "Leonardo", "quem_nosso": "Nosso"}[query.data]
        estado["quem"] = quem

        keyboard = [
            [InlineKeyboardButton(nome, callback_data=cat)]
            for cat, nome in CATEGORIAS.items()
        ]

        await query.message.reply_text(
            f"Quem gastou: *{quem}*\nAgora escolha a categoria do gasto:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Fechamento
    if query.data.startswith("fechar_"):
        if query.data == "fechar_nao":
            await query.message.reply_text("Fechamento cancelado.")
        elif query.data == "fechar_sim":
            for gasto in data["gastos"]:
                if gasto.get("categoria") in ["virtual", "compras"] and gasto.get("parcelas_restantes"]:

                    gasto["parcelas_restantes"] -= 1

            data["gastos"] = [
                g for g in data["gastos"]
                if (
                    g.get("categoria") == "fixo"
                    or g.get("categoria") in ["virtual", "compras"]
                    or g.get("parcelas_restantes", 0) > 0
                )
            ]

            save_data(data)
            await query.message.reply_text("✅ Mês fechado!")
        return

    # Editar
    if query.data.startswith("editar_"):
        idx = int(query.data.split("_")[1])
        gasto = data["gastos"][idx]
        user_state[user_id] = {"edit": idx}
        await query.message.reply_text(
            f"Digite o novo valor para {gasto.get('produto','gasto')} (atual R$ {gasto.get('valor_total', gasto.get('valor',0)):.2f}):"
        )
        return

    # Excluir
    if query.data.startswith("excluir_"):
        idx = int(query.data.split("_")[1])
        data["gastos"].pop(idx)
        save_data(data)
        await query.message.reply_text(f"Gasto excluído com sucesso!")
        return

    # Categoria escolhida
    if not estado or estado.get("valor") is None or estado.get("quem") is None:
        await query.message.reply_text("Erro: valor ou quem gastou não definido.")
        return

    categoria = query.data
    estado["categoria"] = categoria

    # Gasto fixo → pedir nome
    if categoria == "fixo":
        await query.message.reply_text("Digite o nome do gasto fixo:")
        return

    # Gastos parcelados
    if categoria in ["virtual", "compras"]:
        await query.message.reply_text(f"Digite o nome do produto para {CATEGORIAS[categoria]}:")
        return

    # Gasto comum
    valor = estado["valor"]
    data["gastos"].append({
        "quem": estado["quem"],
        "produto": estado.get("produto", ""),
        "categoria": categoria,
        "valor": valor,
        "data": str(datetime.now().date())
    })
    save_data(data)

    await query.message.reply_text(
        f"Gasto registrado!\n👤 Quem: {estado['quem']}\n💸 Categoria: {CATEGORIAS[categoria]}\nValor: R$ {valor:.2f}"
    )

    user_state.pop(user_id)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    estado = user_state.get(user_id)
    data = load_data()

    # Comandos básicos
    if text.lower() == "info":
        await enviar_info(update)
        return

    if text.lower() == "ajuda":
        await enviar_ajuda(update)
        return

    if text.lower() == "gerar resumo":
        caminho = gerar_planilha()
        await update.message.reply_document(open(caminho, "rb"))
        return

    if text.lower() == "fechamento":
        await fechamento(update)
        return

    # Editar valor
    if estado and estado.get("edit") is not None:
        idx = estado["edit"]
        try:
            novo_valor = float(text.replace(",", ".")) if text else 0
            data["gastos"][idx]["valor_total"] = novo_valor

            if data["gastos"][idx].get("parcelas_iniciais"):
                data["gastos"][idx]["parcela_valor"] = novo_valor / data["gastos"][idx]["parcelas_iniciais"]

            save_data(data)
            await update.message.reply_text("Gasto atualizado com sucesso!")
        except:
            await update.message.reply_text("Valor inválido.")
        user_state.pop(user_id)
        return

    # Nome do gasto fixo
    if estado and estado.get("categoria") == "fixo" and not estado.get("produto"):
        estado["produto"] = text.upper()

        data["gastos"].append({
            "quem": estado["quem"],
            "produto": estado["produto"],
            "categoria": "fixo",
            "valor": estado["valor"],
            "fixo_permanente": True,
            "data": str(datetime.now().date())
        })
        save_data(data)

        await update.message.reply_text(
            f"💼 Gasto Fixo Registrado!\n👤 Quem: {estado['quem']}\n🔠 Nome: *{estado['produto']}*\nValor: R$ {estado['valor']:.2f}",
            parse_mode="Markdown"
        )

        user_state.pop(user_id)
        return

    # Produto parcelado
    if estado and estado.get("categoria") in ["virtual", "compras"] and not estado.get("produto"):
        estado["produto"] = text.upper()
        await update.message.reply_text("Agora digite o número de parcelas:")
        return

    # Número de parcelas
    if estado and estado.get("categoria") in ["virtual", "compras"] and estado.get("produto") and not estado.get("parcelas"):
        try:
            parcelas = int(text)
            estado["parcelas"] = parcelas

            valor_total = estado["valor"]
            valor_parcela = valor_total / parcelas

            data["gastos"].append({
                "quem": estado["quem"],
                "produto": estado["produto"],
                "categoria": estado["categoria"],
                "valor_total": valor_total,
                "parcelas_restantes": parcelas,
                "parcelas_iniciais": parcelas,
                "parcela_valor": valor_parcela,
                "ultimo_update": f"{datetime.now().year}-{datetime.now().month}"
            })
            save_data(data)

            await update.message.reply_text(
                f"💳 Compra Registrada!\n👤 Quem: {estado['quem']}\nProduto: {estado['produto']}\nTotal: R$ {valor_total:.2f}\n{parcelas}x de R$ {valor_parcela:.2f}"
            )

            user_state.pop(user_id)
            return

        except:
            await update.message.reply_text("Digite um número de parcelas válido.")
            return

    # Valor inicial
    try:
        valor = float(text.replace(",", "."))
        user_state[user_id] = {"valor": valor}

        keyboard = [
            [
                InlineKeyboardButton("Lissa", callback_data="quem_lissa"),
                InlineKeyboardButton("Leonardo", callback_data="quem_leonardo"),
                InlineKeyboardButton("Nosso", callback_data="quem_nosso")
            ]
        ]

        await update.message.reply_text(
            f"Valor recebido: R$ {valor:.2f}\nQuem fez esse gasto?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except:
        await update.message.reply_text("Digite um valor válido ou use (ajuda).")

# ----------------------
# Info
# ----------------------
async def enviar_info(update: Update):
    atualizar_parcelas()
    data = load_data()

    msg = "📊 *RESUMO DO MÊS*\n\n"
    total_geral = 0

    for idx, gasto in enumerate(data["gastos"]):
        nome = gasto.get("produto", "").upper()

        if gasto["categoria"] in ["virtual", "compras"]:
            parcelas = gasto.get("parcelas_restantes", 0)
            msg += (
                f"{idx+1}. 👤 *{gasto.get('quem','—')}* — *{nome}* "
                f"- {CATEGORIAS[gasto['categoria']]} - R$ {gasto['parcela_valor']:.2f} "
                f"(parcela do mês) ({parcelas} restantes)\n"
            )
            total_geral += gasto.get("parcela_valor", 0)
        else:
            msg += (
                f"{idx+1}. 👤 *{gasto.get('quem','—')}* — *{nome}* "
                f"- {CATEGORIAS[gasto['categoria']]} - R$ {gasto.get('valor',0):.2f}\n"
            )
            total_geral += gasto.get("valor", 0)

    msg += f"\n💰 *TOTAL DO MÊS:* R$ {total_geral:.2f}"

    keyboard = []
    for idx, gasto in enumerate(data["gastos"]):
        keyboard.append([
            InlineKeyboardButton(f"Editar {idx+1}", callback_data=f"editar_{idx}"),
            InlineKeyboardButton(f"Excluir {idx+1}", callback_data=f"excluir_{idx}")
        ])

    await update.message.reply_text(
        msg, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )

# ----------------------
# Ajuda
# ----------------------
async def enviar_ajuda(update: Update):
    msg = (
        "📘 *COMANDOS DISPONÍVEIS*\n"
        "- Digite um valor → o bot pergunta quem gastou\n"
        "- Depois pergunta a categoria\n"
        "- info → ver gastos detalhados\n"
        "- gerar resumo → baixar planilha Excel\n"
        "- fechamento → finalizar mês e atualizar parcelas\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# ----------------------
# Fechamento
# ----------------------
async def fechamento(update: Update):
    atualizar_parcelas()
    data = load_data()

    if not data["gastos"]:
        await update.message.reply_text("Nenhum gasto registrado neste mês.")
        return

    resumo = "📌 *FECHAMENTO DO MÊS*\n\n"
    total_mes = 0

    for gasto in data["gastos"]:
        nome = gasto.get("produto", "").upper()
        quem = gasto.get("quem", "—")

        if gasto["categoria"] in ["virtual", "compras"]:
            parcela = gasto.get("parcela_valor", 0)
            total_mes += parcela
            resumo += (
                f"👤 {quem} — *{nome}* - "
                f"{CATEGORIAS[gasto['categoria']]} - Parcela do mês: R$ {parcela:.2f} "
                f"({gasto.get('parcelas_restantes',0)} restantes)\n"
            )
        else:
            valor = gasto.get("valor", 0)
            total_mes += valor
            resumo += (
                f"👤 {quem} — *{nome}* - "
                f"{CATEGORIAS[gasto['categoria']]} - R$ {valor:.2f}\n"
            )

    resumo += f"\n💰 *TOTAL DO MÊS:* R$ {total_mes:.2f}\n"

    keyboard = [
        [InlineKeyboardButton("Sim", callback_data="fechar_sim"),
         InlineKeyboardButton("Não", callback_data="fechar_nao")]
    ]

    await update.message.reply_text(
        resumo, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ----------------------
# Main
# ----------------------
def main():
    load_dotenv()
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))

    print("Bot rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()
