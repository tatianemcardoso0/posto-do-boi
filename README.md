# Sistema de RH 180° — Posto do Boi & Express do Boi

Plataforma web completa de avaliação de desempenho 180°, com cadastro de colaboradores, dashboard do gestor, feedback automático editável, PDI robusto e exportação em PDF.

## Funcionalidades

- 🔐 Login com dois perfis: **Gestor** e **Colaborador**
- 👥 Cadastro de colaboradores (feito pelo gestor)
- 📋 Questionário 180° já preenchido com 12 critérios para postos de combustível e conveniência
- ✍️ Autoavaliação do colaborador + avaliação do gestor
- 🤖 **Resultados automáticos** com média 180°
- 📝 **Feedback automático e editável** gerado a partir das notas
- 🎯 **PDI robusto** automático com objetivo, ações, prazo e indicadores
- 📊 Dashboard com indicadores: equipe, progresso, nota média, ciclos, unidades
- 📄 Exportação de **relatório completo em PDF**
- 🕓 Histórico de avaliações + log de auditoria de tudo que foi feito
- 🙈 Colaborador **não visualiza** notas, médias, feedback ou relatórios
- 🎨 Design responsivo, profissional, com identidade vermelho/amarelo

## Como executar

```bash
# 1. Crie o ambiente
python -m venv .venv
source .venv/bin/activate          # Linux/Mac
.venv\Scripts\activate             # Windows

# 2. Instale dependências
pip install -r requirements.txt

# 3. Rode o servidor
python app.py
```

Abra **http://localhost:5000**

## Acessos de demonstração

| Perfil       | E-mail                       | Senha   |
|--------------|------------------------------|---------|
| Gestor       | gestor@postodoboi.com        | 123456  |
| Colaborador  | ana@postodoboi.com           | 123456  |
| Colaborador  | bruno@expressdoboi.com       | 123456  |
| Colaborador  | camila@expressdoboi.com      | 123456  |
| Colaborador  | diego@expressdoboi.com       | 123456  |

## Estrutura

```
hr180/
├─ app.py                    # Backend Flask + SQLite + lógica + PDF
├─ requirements.txt
├─ static/style.css          # Tema com cores Posto do Boi
└─ templates/
   ├─ base.html
   ├─ login.html
   ├─ manager_dashboard.html
   ├─ employee_dashboard.html
   ├─ employees.html
   ├─ questions.html
   ├─ cycles.html
   ├─ evaluation_form.html
   ├─ feedback.html
   ├─ history.html
   └─ company_settings.html
```

## Banco de dados

SQLite local (`postodoboi_rh.db`). Persiste todo o histórico:
- Empresa, usuários, perguntas, ciclos
- Atribuições de avaliação, respostas
- Feedback final, PDI, comentários do gestor
- Log de auditoria de cada ação (login, cadastro, avaliação, edição, PDF gerado etc.)

## Fluxo recomendado

1. **Gestor entra** → Dashboard
2. Cadastra colaboradores em **Colaboradores**
3. Cria um ciclo em **Ciclos**
4. **Colaborador entra** → preenche autoavaliação (não vê notas/resultados)
5. **Gestor avalia** o colaborador → sistema gera **feedback automático** + **PDI automático**
6. Gestor edita o feedback/PDI conforme necessário e salva
7. Gestor baixa **PDF** consolidado
8. Tudo fica registrado em **Histórico** + **Log de auditoria**
