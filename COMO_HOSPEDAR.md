# 🚀 Como hospedar online — Passo a passo (gratuito, sem cartão)

Você vai usar o **Render.com**. É gratuito, fica online 24/7 e leva **menos de 10 minutos**.

---

## ✅ Passo 1 — Criar conta no GitHub (2 minutos)

1. Abra [github.com](https://github.com) e clique em **Sign up**
2. Crie sua conta (email + senha)
3. Confirme o email

---

## ✅ Passo 2 — Subir o código para o GitHub (3 minutos)

1. No GitHub, clique no botão verde **New repository**
2. Nome do repositório: `posto-do-boi-rh`
3. Marque **Public** (gratuito)
4. NÃO marque "Add README" (já vem no projeto)
5. Clique em **Create repository**

Na tela seguinte, clique em **uploading an existing file**:

6. Extraia o ZIP do projeto no seu computador
7. **Arraste TODOS os arquivos** da pasta `hr180/` para a página do GitHub
   (arraste de dentro da pasta, não a pasta inteira)
8. Role para baixo, clique em **Commit changes**

---

## ✅ Passo 3 — Hospedar no Render (3 minutos)

1. Abra [render.com](https://render.com) e clique em **Get Started**
2. Clique em **Sign in with GitHub** (use a conta que acabou de criar)
3. Autorize o Render a acessar seu GitHub
4. No painel do Render, clique em **New +** → **Web Service**
5. Selecione o repositório `posto-do-boi-rh`
6. Preencha:
   - **Name:** `posto-do-boi-rh`
   - **Region:** Oregon (US) ou o mais próximo
   - **Branch:** `main`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Instance Type:** **Free**
7. Clique em **Create Web Service**

Aguarde **2 a 5 minutos**. Quando aparecer **"Live"** em verde no topo, está pronto!

---

## ✅ Passo 4 — Acessar o site

O Render vai te dar uma URL parecida com:
```
https://posto-do-boi-rh.onrender.com
```

Abra essa URL no navegador e faça login com:

| Perfil | E-mail | Senha |
|---|---|---|
| **Gestor** | gestor@postodoboi.com | 123456 |
| Colaborador | ana@postodoboi.com | 123456 |

---

## 🆘 Se der erro

- **"Build failed"**: confira se enviou o arquivo `requirements.txt` para o GitHub
- **"Application failed to respond"**: aguarde mais 2 minutos, o primeiro deploy demora
- **Site "dormindo"**: o plano gratuito faz o site "dormir" após 15min sem uso, e demora 30s para acordar. Para evitar, é só usar com mais frequência ou pagar US$7/mês.

---

## 🎁 Alternativa ainda mais fácil — sem precisar de GitHub

Se preferir, use o **PythonAnywhere** (gratuito):

1. Crie conta em [pythonanywhere.com](https://www.pythonanywhere.com) (plano Beginner gratuito)
2. Vá em **Web** → **Add a new web app** → **Flask** → **Python 3.10**
3. No painel **Files**, faça upload do ZIP do projeto
4. Em **Web → WSGI configuration file**, ajuste o caminho para apontar ao `app.py`
5. Clique em **Reload** e acesse a URL gerada

---

Pronto! Qualquer dúvida no caminho, é só me chamar com o print do erro.
