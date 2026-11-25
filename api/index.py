import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import errors
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()  # Lê o .env localmente; na Vercel usa as variáveis do painel

app = Flask(__name__)

STATUS_VALIDOS = ("ativo", "bloqueado")


# ---------- Conexão com o banco ----------
def get_conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL não configurada")
    return psycopg2.connect(url)


def executar(sql, params=None, um=False):
    """Executa uma query, faz commit e devolve o resultado (dict ou lista de dicts)."""
    conn = get_conn()
    try:
        with conn:  # commit automático (rollback em caso de erro)
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                if cur.description is None:
                    return None
                return cur.fetchone() if um else cur.fetchall()
    finally:
        conn.close()


# ---------- Validação ----------
def validar(dados):
    if not dados:
        return "Corpo da requisição vazio ou inválido (envie JSON)."

    campos = ("nome_completo", "matricula", "contato", "status_cadastro")
    for c in campos:
        valor = dados.get(c)
        if not isinstance(valor, str) or not valor.strip():
            return f"O campo '{c}' é obrigatório."

    if len(dados["nome_completo"].strip()) > 150:
        return "nome_completo deve ter no máximo 150 caracteres."
    if len(dados["matricula"].strip()) > 40:
        return "matricula deve ter no máximo 40 caracteres."
    if len(dados["contato"].strip()) > 120:
        return "contato deve ter no máximo 120 caracteres."
    if dados["status_cadastro"] not in STATUS_VALIDOS:
        return "status_cadastro deve ser 'ativo' ou 'bloqueado'."
    return None


# ---------- CREATE ----------
@app.post("/api/leitores")
def criar_leitor():
    dados = request.get_json(silent=True)
    erro = validar(dados)
    if erro:
        return jsonify({"erro": erro}), 400

    leitor = executar(
        """
        INSERT INTO leitor (nome_completo, matricula, contato, status_cadastro)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        (
            dados["nome_completo"].strip(),
            dados["matricula"].strip(),
            dados["contato"].strip(),
            dados["status_cadastro"],
        ),
        um=True,
    )
    return jsonify(leitor), 201


# ---------- READ (todos) ----------
@app.get("/api/leitores")
def listar_leitores():
    leitores = executar("SELECT * FROM leitor ORDER BY id_usuario DESC")
    return jsonify(leitores)


# ---------- READ (um) ----------
@app.get("/api/leitores/<int:id_usuario>")
def buscar_leitor(id_usuario):
    leitor = executar(
        "SELECT * FROM leitor WHERE id_usuario = %s", (id_usuario,), um=True
    )
    if not leitor:
        return jsonify({"erro": "Leitor não encontrado."}), 404
    return jsonify(leitor)


# ---------- UPDATE ----------
@app.put("/api/leitores/<int:id_usuario>")
def atualizar_leitor(id_usuario):
    dados = request.get_json(silent=True)
    erro = validar(dados)
    if erro:
        return jsonify({"erro": erro}), 400

    leitor = executar(
        """
        UPDATE leitor
           SET nome_completo = %s,
               matricula = %s,
               contato = %s,
               status_cadastro = %s
         WHERE id_usuario = %s
        RETURNING *
        """,
        (
            dados["nome_completo"].strip(),
            dados["matricula"].strip(),
            dados["contato"].strip(),
            dados["status_cadastro"],
            id_usuario,
        ),
        um=True,
    )
    if not leitor:
        return jsonify({"erro": "Leitor não encontrado."}), 404
    return jsonify(leitor)


# ---------- DELETE ----------
@app.delete("/api/leitores/<int:id_usuario>")
def deletar_leitor(id_usuario):
    leitor = executar(
        "DELETE FROM leitor WHERE id_usuario = %s RETURNING id_usuario",
        (id_usuario,),
        um=True,
    )
    if not leitor:
        return jsonify({"erro": "Leitor não encontrado."}), 404
    return jsonify({"mensagem": "Leitor excluído com sucesso."})


# ---------- Tratamento de erros ----------
@app.errorhandler(errors.UniqueViolation)
def erro_duplicado(e):
    return jsonify({"erro": "Já existe um leitor com essa matrícula."}), 409


@app.errorhandler(Exception)
def erro_generico(e):
    # Deixa o Flask tratar erros HTTP normais (404, 405...)
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({"erro": e.description}), e.code
    app.logger.exception(e)
    return jsonify({"erro": "Erro interno no servidor."}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)