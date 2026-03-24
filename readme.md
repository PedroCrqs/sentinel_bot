# 🤖 Sentinel Bot

> Bot Python de monitoramento e detecção inteligente de zonas via WhatsApp, com matching semântico, normalização e classificação automática.

---

## ✨ Funcionalidades

- Detecção e classificação automática de zonas
- Matching semântico com normalização de entradas
- Suporte a `sun_type`, `seafront` e tipos de zona
- Limpeza e purge de usuários
- Estrutura modular com classifier, matcher e normalizer

---

## 🛠️ Requisitos

- Python 3.8+
- Dependências listadas em `requirements.txt`

---

## 📦 Instalação

```bash
# Clone o repositório
git clone https://github.com/PedroCrqs/sentinel_bot.git
cd sentinel_bot

# Instale as dependências
pip install -r requirements.txt
```

---

## ▶️ Como usar

```bash
python main.py
```

---

## 🗂️ Estrutura do Projeto

```
sentinel_bot/
├── data/               # Dados de referência (ignorados pelo git)
├── classifier.py       # Classificação de entradas
├── matcher.py          # Matching semântico de zonas
├── normalizer.py       # Normalização de strings
├── main.py             # Ponto de entrada
├── requirements.txt    # Dependências Python
└── .gitignore
```

---

## 📋 Versões

Veja o [CHANGELOG](CHANGELOG.md) para o histórico completo de versões.

| Versão | Destaque |
|--------|----------|
| v1.3.0 | Zone matching, sun_type, seafront e normalização |
| v1.2.0 | Dados e estrutura de cleaner |
| v1.1.0 | Matcher aprimorado |
| v1.0.0 | Primeiro release estável |

---

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
