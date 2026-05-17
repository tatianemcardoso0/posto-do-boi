from __future__ import annotations

import io
import os
from datetime import datetime, date
from functools import wraps
from io import BytesIO
from statistics import mean

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from flask import (
    Flask, flash, g, redirect, render_template, request,
    send_file, session, url_for,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, KeepTogether,
)

app = Flask(__name__)
app.config[BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)

DB_PATH = os.path.join(INSTANCE_DIR, 'postodoboi_rh.db')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'postodoboi-rh-secret'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'postodoboi-rh-secret'

db = SQLAlchemy(app)

# Cores Ipiranga
IPIRANGA_BLUE = '#003B7A'
IPIRANGA_BLUE_DARK = '#001f44'
IPIRANGA_YELLOW = '#FFCC00'
IPIRANGA_YELLOW_DARK = '#e6b800'


# =========================================================
# MODELOS
# =========================================================
class CompanyBrand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, default='Posto do Boi e Express do Boi')
    mission = db.Column(db.Text, nullable=False, default='Combustível, conveniência e atendimento de excelência para o nosso cliente todos os dias.')
    values = db.Column(db.Text, nullable=False, default='Atendimento de verdade\nSegurança em primeiro lugar\nDisciplina operacional\nTrabalho em equipe\nResponsabilidade com o cliente')
    primary_color = db.Column(db.String(20), nullable=False, default='#003B7A')
    secondary_color = db.Column(db.String(20), nullable=False, default='#FFCC00')


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    department = db.Column(db.String(120), nullable=False)
    position = db.Column(db.String(120), nullable=False)
    unit = db.Column(db.String(120), nullable=False, default='Posto do Boi')
    admission_date = db.Column(db.Date, nullable=True)
    active = db.Column(db.Boolean, default=True)
    manager_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    manager = db.relationship('User', remote_side=[id], backref='team_members')

    def set_password(self, raw: str):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(120), nullable=False)
    text = db.Column(db.Text, nullable=False)
    expected_behavior = db.Column(db.Text, nullable=True)
    active = db.Column(db.Boolean, default=True)


class EvaluationCycle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='draft')


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey('evaluation_cycle.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    manager_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cycle = db.relationship('EvaluationCycle', backref='assignments')
    employee = db.relationship('User', foreign_keys=[employee_id], backref='employee_assignments')
    manager = db.relationship('User', foreign_keys=[manager_id], backref='manager_assignments')


class Response(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    evaluator_role = db.Column(db.String(20), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    assignment = db.relationship('Assignment', backref='responses')
    question = db.relationship('Question')


class FinalFeedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), unique=True, nullable=False)
    overall_score = db.Column(db.Float, nullable=True)
    profile_label = db.Column(db.String(80), nullable=True)
    strengths = db.Column(db.Text, nullable=False, default='')
    development_points = db.Column(db.Text, nullable=False, default='')
    auto_feedback = db.Column(db.Text, nullable=False, default='')
    editable_feedback = db.Column(db.Text, nullable=False, default='')
    auto_pdi = db.Column(db.Text, nullable=False, default='')
    editable_pdi = db.Column(db.Text, nullable=False, default='')
    manager_comments = db.Column(db.Text, nullable=False, default='')
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    assignment = db.relationship('Assignment', backref=db.backref('final_feedback', uselist=False))


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(160), nullable=False)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.String(40), nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User')


# =========================================================
# CONTEXTO GLOBAL
# =========================================================
@app.before_request
def load_globals():
    g.company_brand = CompanyBrand.query.first()
    user_id = session.get('user_id')
    g.current_user = User.query.get(user_id) if user_id else None


@app.context_processor
def inject_globals():
    return {
        'company_brand': g.get('company_brand'),
        'current_user': g.get('current_user'),
        'today': date.today(),
    }


def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not g.current_user:
                return redirect(url_for('login'))
            if role and g.current_user.role != role:
                flash('Você não tem permissão para acessar esta área.', 'danger')
                return redirect(url_for('employee_dashboard' if g.current_user.role == 'employee' else 'manager_dashboard'))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def log_action(action, entity_type, entity_id=None, details=''):
    user = g.get('current_user')
    db.session.add(AuditLog(
        user_id=user.id if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details,
    ))
    db.session.commit()


# =========================================================
# REGRAS DE NEGÓCIO
# =========================================================
def score_label(score):
    if score is None:
        return 'Sem avaliação'
    if score >= 4.5:
        return 'Destaque'
    if score >= 4.0:
        return 'Performance consistente'
    if score >= 3.0:
        return 'Bom desempenho com oportunidades'
    if score >= 2.0:
        return 'Atenção ao desenvolvimento'
    return 'Crítico para intervenção'


def score_color_hex(score):
    if score is None:
        return '#94a3b8'
    if score >= 4.5:
        return '#15803d'
    if score >= 4.0:
        return '#16a34a'
    if score >= 3.0:
        return '#ca8a04'
    if score >= 2.0:
        return '#ea580c'
    return '#dc2626'


def assignment_progress(assignment: Assignment):
    active_questions = Question.query.filter_by(active=True).count()
    emp_count = Response.query.filter_by(assignment_id=assignment.id, evaluator_role='employee').count()
    mgr_count = Response.query.filter_by(assignment_id=assignment.id, evaluator_role='manager').count()
    emp_done = active_questions > 0 and emp_count >= active_questions
    mgr_done = active_questions > 0 and mgr_count >= active_questions
    return {
        'employee_done': emp_done,
        'manager_done': mgr_done,
        'percent': int(((emp_count + mgr_count) / max(active_questions * 2, 1)) * 100),
    }


def grouped_responses(assignment_id: int):
    questions = Question.query.filter_by(active=True).order_by(Question.category, Question.id).all()
    data = []
    for q in questions:
        emp = Response.query.filter_by(assignment_id=assignment_id, question_id=q.id, evaluator_role='employee').first()
        mgr = Response.query.filter_by(assignment_id=assignment_id, question_id=q.id, evaluator_role='manager').first()
        final = None
        scores = [r.score for r in [emp, mgr] if r]
        if scores:
            final = round(mean(scores), 1)
        data.append({'question': q, 'employee': emp, 'manager': mgr, 'final_score': final})
    return data


def calculate_summary(assignment_id: int):
    rows = grouped_responses(assignment_id)
    emp_scores = [r['employee'].score for r in rows if r['employee']]
    mgr_scores = [r['manager'].score for r in rows if r['manager']]
    final_scores = [r['final_score'] for r in rows if r['final_score'] is not None]
    by_category = {}
    by_category_emp = {}
    by_category_mgr = {}
    for r in rows:
        if r['final_score'] is not None:
            by_category.setdefault(r['question'].category, []).append(r['final_score'])
        if r['employee']:
            by_category_emp.setdefault(r['question'].category, []).append(r['employee'].score)
        if r['manager']:
            by_category_mgr.setdefault(r['question'].category, []).append(r['manager'].score)
    category_avg = [{'category': c, 'score': round(mean(v), 2)} for c, v in by_category.items()]
    category_avg.sort(key=lambda x: x['score'], reverse=True)
    category_compare = []
    for cat in by_category.keys():
        category_compare.append({
            'category': cat,
            'employee': round(mean(by_category_emp.get(cat, [0])), 2) if by_category_emp.get(cat) else 0,
            'manager': round(mean(by_category_mgr.get(cat, [0])), 2) if by_category_mgr.get(cat) else 0,
            'final': round(mean(by_category[cat]), 2),
        })
    return {
        'rows': rows,
        'employee_avg': round(mean(emp_scores), 2) if emp_scores else 0,
        'manager_avg': round(mean(mgr_scores), 2) if mgr_scores else 0,
        'final_avg': round(mean(final_scores), 2) if final_scores else 0,
        'category_avg': category_avg,
        'category_compare': category_compare,
    }


def history_for_employee(employee_id, current_assignment_id=None):
    assignments = Assignment.query.filter_by(employee_id=employee_id).order_by(Assignment.id.desc()).all()
    history = []
    for a in assignments:
        if current_assignment_id and a.id == current_assignment_id:
            continue
        s = calculate_summary(a.id)
        if s['final_avg'] > 0:
            history.append({
                'cycle': a.cycle.name,
                'date': a.cycle.end_date,
                'final_avg': s['final_avg'],
                'employee_avg': s['employee_avg'],
                'manager_avg': s['manager_avg'],
            })
    return history


def build_auto_feedback(assignment, summary):
    overall = summary['final_avg']
    profile = score_label(overall)
    strengths = [c for c in summary['category_avg'] if c['score'] >= 4.0][:3]
    development = [c for c in sorted(summary['category_avg'], key=lambda x: x['score']) if c['score'] < 4.0][:3]
    if not strengths and summary['category_avg']:
        strengths = sorted(summary['category_avg'], key=lambda x: x['score'], reverse=True)[:2]
    if not development and summary['category_avg']:
        development = sorted(summary['category_avg'], key=lambda x: x['score'])[:2]

    p1 = (
        f"{assignment.employee.name} concluiu o ciclo {assignment.cycle.name} com média final de "
        f"{overall:.2f}, enquadrando-se no perfil '{profile}'. A análise considera a autoavaliação "
        f"({summary['employee_avg']}) e a percepção do gestor ({summary['manager_avg']}), "
        f"consolidando uma visão 180° do desempenho."
    )
    if strengths:
        p2 = "Como pontos fortes, destacam-se: " + ", ".join(
            f"{s['category']} ({s['score']:.1f})" for s in strengths
        ) + ". São competências que devem ser preservadas e usadas para impulsionar a equipe."
    else:
        p2 = "Não há competências claramente acima da média neste ciclo; o foco deve ser construir consistência."

    if development:
        p3 = "Como prioridades de desenvolvimento, atenção especial para: " + ", ".join(
            f"{d['category']} ({d['score']:.1f})" for d in development
        ) + ". Estas áreas devem ser trabalhadas com plano de ação e checkpoints periódicos."
    else:
        p3 = "Sem lacunas críticas identificadas. Recomenda-se manter o nível atual e buscar excelência operacional."

    return "\n\n".join([p1, p2, p3]), strengths, development


def build_auto_pdi(strengths, development):
    blocks = []
    for idx, item in enumerate(development, start=1):
        blocks.append(
            f"{idx}) Competência: {item['category']} (nota atual {item['score']:.1f})\n"
            f"   Objetivo: elevar a competência para nota mínima 4,0 no próximo ciclo.\n"
            f"   Ações: treinamento prático no posto, acompanhamento do gestor, observação direta no atendimento.\n"
            f"   Prazo: 30 / 60 / 90 dias.\n"
            f"   Indicador de sucesso: registrar 3 evidências concretas de evolução + nota >= 4,0."
        )
    if strengths:
        blocks.append(
            "Reforço de pontos fortes: usar {nomes} para mentorar colegas e padronizar boas práticas na unidade.".format(
                nomes=", ".join(s['category'] for s in strengths)
            )
        )
    if not blocks:
        blocks.append("Sem ações estruturadas neste ciclo. Reavaliar após próxima avaliação 180°.")
    return "\n\n".join(blocks)


def regenerate_feedback(assignment: Assignment):
    summary = calculate_summary(assignment.id)
    feedback_text, strengths, development = build_auto_feedback(assignment, summary)
    pdi_text = build_auto_pdi(strengths, development)

    feedback = assignment.final_feedback
    if not feedback:
        feedback = FinalFeedback(assignment_id=assignment.id)
        db.session.add(feedback)

    feedback.overall_score = summary['final_avg']
    feedback.profile_label = score_label(summary['final_avg'])
    feedback.strengths = "; ".join(f"{s['category']} ({s['score']:.1f})" for s in strengths) if strengths else ''
    feedback.development_points = "; ".join(f"{d['category']} ({d['score']:.1f})" for d in development) if development else ''
    feedback.auto_feedback = feedback_text
    if not feedback.editable_feedback:
        feedback.editable_feedback = feedback_text
    feedback.auto_pdi = pdi_text
    if not feedback.editable_pdi:
        feedback.editable_pdi = pdi_text
    feedback.generated_at = datetime.utcnow()
    db.session.commit()
    return feedback


# =========================================================
# GERAÇÃO DE GRÁFICOS PARA O PDF
# =========================================================
def generate_bar_chart(category_compare):
    """Gráfico de barras horizontal comparando auto vs gestor por competência"""
    if not category_compare:
        return None
    fig, ax = plt.subplots(figsize=(7, max(3, len(category_compare) * 0.55)), dpi=120)
    categories = [c['category'] for c in category_compare]
    emp_scores = [c['employee'] for c in category_compare]
    mgr_scores = [c['manager'] for c in category_compare]

    y_pos = np.arange(len(categories))
    height = 0.38
    ax.barh(y_pos - height/2, emp_scores, height, label='Autoavaliação', color=IPIRANGA_YELLOW, edgecolor='#1a1a1a', linewidth=0.5)
    ax.barh(y_pos + height/2, mgr_scores, height, label='Gestor', color=IPIRANGA_BLUE, edgecolor='#1a1a1a', linewidth=0.5)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(categories, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 5.5)
    ax.set_xlabel('Nota (1 a 5)', fontsize=9)
    ax.set_title('Comparativo por Competência', fontsize=11, fontweight='bold', color=IPIRANGA_BLUE)
    ax.legend(loc='lower right', fontsize=9, frameon=True)
    ax.grid(axis='x', linestyle='--', alpha=0.4)
    ax.set_axisbelow(True)
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)

    for i, (e, m) in enumerate(zip(emp_scores, mgr_scores)):
        if e > 0:
            ax.text(e + 0.05, i - height/2, f'{e:.1f}', va='center', fontsize=8)
        if m > 0:
            ax.text(m + 0.05, i + height/2, f'{m:.1f}', va='center', fontsize=8)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=120, facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_radar_chart(category_compare):
    """Gráfico de radar (teia de aranha)"""
    if len(category_compare) < 3:
        return None
    categories = [c['category'] for c in category_compare]
    emp_scores = [c['employee'] for c in category_compare]
    mgr_scores = [c['manager'] for c in category_compare]

    N = len(categories)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]

    emp_values = emp_scores + emp_scores[:1]
    mgr_values = mgr_scores + mgr_scores[:1]

    fig, ax = plt.subplots(figsize=(6, 6), dpi=120, subplot_kw=dict(polar=True))
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    plt.xticks(angles[:-1], categories, fontsize=8, color='#1a1a1a')
    ax.set_rlabel_position(0)
    plt.yticks([1, 2, 3, 4, 5], ['1', '2', '3', '4', '5'], color='#64748b', size=7)
    plt.ylim(0, 5)

    ax.plot(angles, emp_values, linewidth=2, linestyle='solid', label='Autoavaliação', color=IPIRANGA_YELLOW_DARK)
    ax.fill(angles, emp_values, IPIRANGA_YELLOW, alpha=0.25)
    ax.plot(angles, mgr_values, linewidth=2, linestyle='solid', label='Gestor', color=IPIRANGA_BLUE)
    ax.fill(angles, mgr_values, IPIRANGA_BLUE, alpha=0.20)

    plt.title('Mapa de Competências 180°', fontsize=12, fontweight='bold', color=IPIRANGA_BLUE, y=1.10)
    plt.legend(loc='upper right', bbox_to_anchor=(1.30, 1.10), fontsize=9, frameon=True)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=120, facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_history_chart(history, current_score):
    """Gráfico de evolução histórica do colaborador"""
    if not history:
        return None
    all_data = list(reversed(history)) + [{'cycle': 'Ciclo atual', 'final_avg': current_score}]
    labels = [h['cycle'][:20] for h in all_data]
    scores = [h['final_avg'] for h in all_data]

    fig, ax = plt.subplots(figsize=(7, 3.2), dpi=120)
    x = range(len(labels))
    ax.plot(x, scores, marker='o', markersize=10, linewidth=2.5, color=IPIRANGA_BLUE)
    ax.fill_between(x, scores, alpha=0.15, color=IPIRANGA_BLUE)

    for i, s in enumerate(scores):
        ax.text(i, s + 0.15, f'{s:.2f}', ha='center', fontsize=9, fontweight='bold', color=IPIRANGA_BLUE)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8, rotation=15, ha='right')
    ax.set_ylim(0, 5.5)
    ax.set_ylabel('Nota final', fontsize=9)
    ax.set_title('Evolução Histórica do Colaborador', fontsize=11, fontweight='bold', color=IPIRANGA_BLUE)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.set_axisbelow(True)
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=120, facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return buf


# =========================================================
# ROTAS
# =========================================================
@app.route('/', methods=['GET', 'POST'])
def login():
    if g.get('current_user'):
        return redirect(url_for('manager_dashboard' if g.current_user.role == 'manager' else 'employee_dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and user.active and user.check_password(password):
            session['user_id'] = user.id
            g.current_user = user
            log_action('Login realizado', 'auth', user.id, f'Perfil {user.role}')
            flash('Login realizado com sucesso.', 'success')
            return redirect(url_for('manager_dashboard' if user.role == 'manager' else 'employee_dashboard'))
        flash('Credenciais inválidas ou usuário inativo.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    if g.get('current_user'):
        log_action('Logout', 'auth', g.current_user.id, 'Sessão encerrada')
    session.clear()
    flash('Sessão encerrada.', 'info')
    return redirect(url_for('login'))


@app.route('/manager/dashboard')
@login_required(role='manager')
def manager_dashboard():
    active_cycle = EvaluationCycle.query.filter_by(status='active').order_by(EvaluationCycle.id.desc()).first()
    team = Assignment.query.filter_by(manager_id=g.current_user.id).all()
    progress_data = [assignment_progress(a) for a in team]
    feedbacks = [a.final_feedback for a in team if a.final_feedback and a.final_feedback.overall_score is not None]
    avg_score = round(mean([f.overall_score for f in feedbacks]), 2) if feedbacks else 0

    by_unit = {}
    for a in team:
        unit = a.employee.unit or 'Sem unidade'
        by_unit.setdefault(unit, {'team': 0, 'completed': 0})
        by_unit[unit]['team'] += 1
        if a.final_feedback and a.final_feedback.overall_score is not None:
            by_unit[unit]['completed'] += 1

    metrics = {
        'team_size': len(team),
        'completed': sum(1 for p in progress_data if p['employee_done'] and p['manager_done']),
        'in_progress': sum(1 for p in progress_data if p['percent'] > 0 and not (p['employee_done'] and p['manager_done'])),
        'avg_progress': int(mean([p['percent'] for p in progress_data])) if progress_data else 0,
        'avg_score': avg_score,
        'units': by_unit,
        'cycles_open': EvaluationCycle.query.filter_by(status='active').count(),
        'employees_total': User.query.filter_by(role='employee', active=True).count(),
    }
    return render_template('manager_dashboard.html', active_cycle=active_cycle,
                           assignments=team, progress_data=progress_data, metrics=metrics)


@app.route('/employee/dashboard')
@login_required(role='employee')
def employee_dashboard():
    assignments = Assignment.query.filter_by(employee_id=g.current_user.id).all()
    active_assignment = next((a for a in assignments if a.cycle.status == 'active'), None)
    active_questions = Question.query.filter_by(active=True).count()
    progress = assignment_progress(active_assignment) if active_assignment else {'percent': 0, 'employee_done': False, 'manager_done': False}
    return render_template('employee_dashboard.html', assignments=assignments,
                           active_assignment=active_assignment, active_questions=active_questions, progress=progress)


@app.route('/company-settings', methods=['GET', 'POST'])
@login_required(role='manager')
def company_settings():
    brand = CompanyBrand.query.first()
    if request.method == 'POST':
        brand.name = request.form['name']
        brand.mission = request.form['mission']
        brand.values = request.form['values']
        brand.primary_color = request.form['primary_color']
        brand.secondary_color = request.form['secondary_color']
        ok, err = safe_commit()
if not ok:
    flash(f'Erro ao atualizar empresa: {err}', 'danger')
    return redirect(url_for('company_settings'))
        log_action('Atualizou dados da empresa', 'company', brand.id, brand.name)
        flash('Identidade da empresa atualizada.', 'success')
        return redirect(url_for('company_settings'))
    return render_template('company_settings.html', brand=brand)


@app.route('/employees', methods=['GET', 'POST'])
@login_required(role='manager')
def employees():
    managers = User.query.filter_by(role='manager').all()
    if request.method == 'POST':
        admission_str = request.form.get('admission_date', '').strip()
        user = User(
            name=request.form['name'].strip(),
            email=request.form['email'].strip().lower(),
            role='employee',
            department=request.form['department'].strip(),
            position=request.form['position'].strip(),
            unit=request.form.get('unit', 'Posto do Boi').strip() or 'Posto do Boi',
            admission_date=datetime.strptime(admission_str, '%Y-%m-%d').date() if admission_str else None,
            manager_id=int(request.form['manager_id']),
            active=True,
        )
        user.set_password(request.form.get('password') or '123456')
        db.session.add(user)
ok, err = safe_commit()
if not ok:
    flash(f'Erro ao salvar colaborador: {err}', 'danger')
    return redirect(url_for('employees'))

log_action('Cadastrou colaborador', 'user', user.id, user.name)
flash(f'Colaborador {user.name} cadastrado com sucesso.', 'success')
        return redirect(url_for('employees'))
    employees_list = User.query.filter_by(role='employee').order_by(User.name).all()
    return render_template('employees.html', employees=employees_list, managers=managers)


@app.route('/employees/<int:user_id>/toggle')
@login_required(role='manager')
def toggle_employee(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'manager':
        flash('Não é possível inativar um gestor por aqui.', 'warning')
        return redirect(url_for('employees'))
    user.active = not user.active
    db.session.commit()
    log_action('Alterou status do colaborador', 'user', user.id, f'Ativo={user.active}')
    flash('Status do colaborador atualizado.', 'info')
    return redirect(url_for('employees'))
@app.route('/employees/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required(role='manager')
def edit_employee(user_id):
    user = User.query.get_or_404(user_id)

    if user.role != 'employee':
        flash('Somente colaboradores podem ser editados por aqui.', 'warning')
        return redirect(url_for('employees'))

    managers = User.query.filter_by(role='manager').order_by(User.name).all()

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        email_exists = User.query.filter(User.email == email, User.id != user.id).first()
        if email_exists:
            flash('Já existe outro usuário com este e-mail.', 'danger')
            return redirect(url_for('edit_employee', user_id=user.id))

        user.name = request.form.get('name', '').strip()
        user.email = email
        user.department = request.form.get('department', '').strip()
        user.position = request.form.get('position', '').strip()
        user.unit = request.form.get('unit', '').strip()

        manager_id = request.form.get('manager_id')
        user.manager_id = int(manager_id) if manager_id else None

        admission_date = request.form.get('admission_date')
        if admission_date:
            user.admission_date = datetime.strptime(admission_date, '%Y-%m-%d').date()
        else:
            user.admission_date = None

        new_password = request.form.get('password', '').strip()
        if new_password:
            user.set_password(new_password)

        db.session.commit()
        flash('Colaborador atualizado com sucesso.', 'success')
        return redirect(url_for('employees'))

    return render_template('edit_employee.html', employee=user, managers=managers)

@app.route('/questions', methods=['GET', 'POST'])
@login_required(role='manager')
def questions():
    if request.method == 'POST':
        question = Question(
            category=request.form['category'].strip(),
            text=request.form['text'].strip(),
            expected_behavior=request.form.get('expected_behavior', '').strip(),
            active=True,
        )
        db.session.add(question)
ok, err = safe_commit()
if not ok:
    flash(f'Erro ao salvar pergunta: {err}', 'danger')
    return redirect(url_for('questions'))
        log_action('Cadastrou pergunta', 'question', question.id, question.category)
        flash('Pergunta adicionada ao questionário.', 'success')
        return redirect(url_for('questions'))
    questions_list = Question.query.order_by(Question.category, Question.id).all()
    return render_template('questions.html', questions=questions_list)


@app.route('/questions/<int:question_id>/toggle')
@login_required(role='manager')
def toggle_question(question_id):
    question = Question.query.get_or_404(question_id)
    question.active = not question.active
    db.session.commit()
    log_action('Alterou status da pergunta', 'question', question.id, f'Ativa={question.active}')
    flash('Status da pergunta atualizado.', 'info')
    return redirect(url_for('questions'))


@app.route('/cycles', methods=['GET', 'POST'])
@login_required(role='manager')
def cycles():
    employees_list = User.query.filter_by(role='employee', active=True).order_by(User.name).all()
    cycles_list = EvaluationCycle.query.order_by(EvaluationCycle.id.desc()).all()
    if request.method == 'POST':
        cycle = EvaluationCycle(
            name=request.form['name'].strip(),
            start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(request.form['end_date'], '%Y-%m-%d').date(),
            status=request.form['status'],
        )
        db.session.add(cycle)
        db.session.flush()
        for employee in employees_list:
            if request.form.get(f'employee_{employee.id}'):
                db.session.add(Assignment(
                    cycle_id=cycle.id,
                    employee_id=employee.id,
                    manager_id=employee.manager_id or g.current_user.id,
                ))
        if cycle.status == 'active':
            EvaluationCycle.query.filter(EvaluationCycle.id != cycle.id, EvaluationCycle.status == 'active').update({'status': 'closed'})
        db.session.commit()
        log_action('Criou ciclo', 'cycle', cycle.id, cycle.name)
        flash('Ciclo criado e colaboradores vinculados.', 'success')
        return redirect(url_for('cycles'))
    return render_template('cycles.html', cycles=cycles_list, employees=employees_list)


@app.route('/evaluation/self/<int:assignment_id>', methods=['GET', 'POST'])
@login_required(role='employee')
def self_evaluation(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.employee_id != g.current_user.id:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('employee_dashboard'))
    questions_list = Question.query.filter_by(active=True).order_by(Question.category, Question.id).all()
    if request.method == 'POST':
        Response.query.filter_by(assignment_id=assignment.id, evaluator_role='employee').delete()
        for q in questions_list:
            score = int(request.form.get(f'score_{q.id}', 0))
            comment = request.form.get(f'comment_{q.id}', '').strip()
            if score:
                db.session.add(Response(
                    assignment_id=assignment.id, question_id=q.id,
                    evaluator_role='employee', score=score, comment=comment,
                ))
        ok, err = safe_commit()
if not ok:
    flash(f'Erro ao salvar autoavaliação: {err}', 'danger')
    return redirect(url_for('self_evaluation', assignment_id=assignment.id))
        log_action('Concluiu autoavaliação', 'assignment', assignment.id, assignment.cycle.name)
        flash('Autoavaliação enviada com sucesso. O resultado consolidado fica disponível apenas para o gestor.', 'success')
        return redirect(url_for('employee_dashboard'))
    existing = {r.question_id: r for r in Response.query.filter_by(assignment_id=assignment.id, evaluator_role='employee').all()}
    return render_template('evaluation_form.html', assignment=assignment, questions=questions_list, existing=existing, mode='employee')


@app.route('/evaluation/manager/<int:assignment_id>', methods=['GET', 'POST'])
@login_required(role='manager')
def manager_evaluation(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.manager_id != g.current_user.id:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('manager_dashboard'))
    questions_list = Question.query.filter_by(active=True).order_by(Question.category, Question.id).all()
    if request.method == 'POST':
        Response.query.filter_by(assignment_id=assignment.id, evaluator_role='manager').delete()
        for q in questions_list:
            score = int(request.form.get(f'score_{q.id}', 0))
            comment = request.form.get(f'comment_{q.id}', '').strip()
            if score:
                db.session.add(Response(
                    assignment_id=assignment.id, question_id=q.id,
                    evaluator_role='manager', score=score, comment=comment,
                ))ok, err = safe_commit()
if not ok:
    flash(f'Erro ao salvar avaliação do gestor: {err}', 'danger')
    return redirect(url_for('manager_evaluation', assignment_id=assignment.id))

regenerate_feedback(assignment)
        log_action('Concluiu avaliação do gestor', 'assignment', assignment.id, assignment.employee.name)
        flash('Avaliação do gestor registrada e feedback automático gerado.', 'success')
        return redirect(url_for('feedback_view', assignment_id=assignment.id))
    existing = {r.question_id: r for r in Response.query.filter_by(assignment_id=assignment.id, evaluator_role='manager').all()}
    return render_template('evaluation_form.html', assignment=assignment, questions=questions_list, existing=existing, mode='manager')


@app.route('/feedback/<int:assignment_id>', methods=['GET', 'POST'])
@login_required(role='manager')
def feedback_view(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.manager_id != g.current_user.id:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('manager_dashboard'))
    feedback = assignment.final_feedback or regenerate_feedback(assignment)
    summary = calculate_summary(assignment.id)
    if request.method == 'POST':
        feedback.editable_feedback = request.form.get('editable_feedback', '')
        feedback.editable_pdi = request.form.get('editable_pdi', '')
        feedback.manager_comments = request.form.get('manager_comments', '')
        db.session.commit()
        log_action('Editou feedback e PDI', 'feedback', feedback.id, assignment.employee.name)
        flash('Feedback e PDI atualizados.', 'success')
        return redirect(url_for('feedback_view', assignment_id=assignment.id))
    return render_template('feedback.html', assignment=assignment, feedback=feedback, summary=summary)


@app.route('/feedback/<int:assignment_id>/regenerate')
@login_required(role='manager')
def feedback_regenerate(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.manager_id != g.current_user.id:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('manager_dashboard'))
    feedback = assignment.final_feedback
    if feedback:
        feedback.editable_feedback = ''
        feedback.editable_pdi = ''
        db.session.commit()
    regenerate_feedback(assignment)
    log_action('Regenerou feedback/PDI', 'feedback', assignment.id, assignment.employee.name)
    flash('Feedback e PDI regenerados a partir das notas atuais.', 'info')
    return redirect(url_for('feedback_view', assignment_id=assignment.id))


@app.route('/history')
@login_required(role='manager')
def history():
    assignments = Assignment.query.filter_by(manager_id=g.current_user.id).order_by(Assignment.id.desc()).all()
    cards = []
    for assignment in assignments:
        summary = calculate_summary(assignment.id)
        cards.append({'assignment': assignment, 'summary': summary, 'progress': assignment_progress(assignment)})
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(80).all()
    return render_template('history.html', cards=cards, logs=logs)


# =========================================================
# PDF — RELATÓRIO PROFISSIONAL COMPLETO
# =========================================================
@app.route('/report/<int:assignment_id>/pdf')
@login_required(role='manager')
def report_pdf(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    if assignment.manager_id != g.current_user.id:
        flash('Acesso não autorizado.', 'danger')
        return redirect(url_for('manager_dashboard'))

    summary = calculate_summary(assignment.id)
    feedback = assignment.final_feedback or regenerate_feedback(assignment)
    brand = CompanyBrand.query.first()
    history_data = history_for_employee(assignment.employee_id, current_assignment_id=assignment.id)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=1.5 * cm, leftMargin=1.5 * cm,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        title=f'Relatório 180° - {assignment.employee.name}',
    )
    base = getSampleStyleSheet()
    primary = colors.HexColor(IPIRANGA_BLUE)
    primary_dark = colors.HexColor(IPIRANGA_BLUE_DARK)
    secondary = colors.HexColor(IPIRANGA_YELLOW)
    grey = colors.HexColor('#475569')
    light = colors.HexColor('#f1f5f9')

    styles = {
        'cover_kicker': ParagraphStyle('CK', parent=base['Normal'], fontSize=11,
                                       textColor=secondary, alignment=TA_CENTER, spaceAfter=8,
                                       fontName='Helvetica-Bold', leading=14),
        'cover_title': ParagraphStyle('CT', parent=base['Title'], fontSize=32,
                                      textColor=colors.white, alignment=TA_CENTER,
                                      spaceAfter=14, leading=36, fontName='Helvetica-Bold'),
        'cover_sub': ParagraphStyle('CS', parent=base['Normal'], fontSize=15,
                                    textColor=colors.white, alignment=TA_CENTER, spaceAfter=12, leading=18),
        'cover_name': ParagraphStyle('CN', parent=base['Normal'], fontSize=22,
                                     textColor=secondary, alignment=TA_CENTER, spaceAfter=8,
                                     fontName='Helvetica-Bold', leading=26),
        'cover_meta': ParagraphStyle('CM', parent=base['Normal'], fontSize=12,
                                     textColor=colors.white, alignment=TA_CENTER, spaceAfter=6, leading=15),
        'h1': ParagraphStyle('H1', parent=base['Heading1'], fontSize=18, textColor=primary,
                             spaceAfter=10, spaceBefore=6, fontName='Helvetica-Bold'),
        'h2': ParagraphStyle('H2', parent=base['Heading2'], fontSize=14, textColor=primary,
                             spaceAfter=8, spaceBefore=10, fontName='Helvetica-Bold'),
        'h3': ParagraphStyle('H3', parent=base['Heading3'], fontSize=12, textColor=primary_dark,
                             spaceAfter=6, fontName='Helvetica-Bold'),
        'body': ParagraphStyle('B', parent=base['BodyText'], fontSize=10, leading=14, alignment=TA_JUSTIFY),
        'body_left': ParagraphStyle('BL', parent=base['BodyText'], fontSize=10, leading=14),
        'small': ParagraphStyle('S', parent=base['BodyText'], fontSize=9, leading=12, textColor=grey),
        'metric_lbl': ParagraphStyle('ML', parent=base['Normal'], fontSize=9, textColor=colors.white,
                                     alignment=TA_CENTER, fontName='Helvetica-Bold'),
        'metric_val': ParagraphStyle('MV', parent=base['Normal'], fontSize=22, textColor=colors.white,
                                     alignment=TA_CENTER, fontName='Helvetica-Bold', leading=26),
    }

    def page_decorator(canvas, doc_):
        canvas.saveState()
        canvas.setFillColor(primary)
        canvas.rect(0, A4[1] - 1*cm, A4[0], 1*cm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica-Bold', 9)
        canvas.drawString(1.5*cm, A4[1] - 0.65*cm, brand.name)
        canvas.drawRightString(A4[0] - 1.5*cm, A4[1] - 0.65*cm, 'Relatório de Avaliação 180°')
        canvas.setFillColor(grey)
        canvas.setFont('Helvetica', 8)
        canvas.drawString(1.5*cm, 0.7*cm, f'Gerado em {datetime.utcnow().strftime("%d/%m/%Y %H:%M")}')
        canvas.drawRightString(A4[0] - 1.5*cm, 0.7*cm, f'Página {doc_.page}')
        canvas.setStrokeColor(secondary)
        canvas.setLineWidth(2)
        canvas.line(1.5*cm, 1*cm, A4[0] - 1.5*cm, 1*cm)
        canvas.restoreState()

    story = []

    # =========================
    # CAPA
    # =========================
    cover_table = Table(
        [[Paragraph('POSTO DO BOI &amp; EXPRESS DO BOI', styles['cover_kicker'])],
         [Spacer(1, 8)],
         [Paragraph('RELATÓRIO DE<br/>AVALIAÇÃO 180°', styles['cover_title'])],
         [Spacer(1, 14)],
         [Paragraph(assignment.employee.name.upper(), styles['cover_name'])],
         [Paragraph(f'{assignment.employee.position} • {assignment.employee.department}', styles['cover_sub'])],
         [Paragraph(f'Unidade: {assignment.employee.unit}', styles['cover_meta'])],
         [Spacer(1, 30)],
         [Paragraph(f'Ciclo: <b>{assignment.cycle.name}</b>', styles['cover_meta'])],
         [Paragraph(f'Período: {assignment.cycle.start_date.strftime("%d/%m/%Y")} a {assignment.cycle.end_date.strftime("%d/%m/%Y")}', styles['cover_meta'])],
         [Paragraph(f'Gestor responsável: <b>{assignment.manager.name}</b>', styles['cover_meta'])],
         [Spacer(1, 40)],
         [Paragraph(f'NOTA FINAL CONSOLIDADA<br/><font size="46">{summary["final_avg"]:.2f}</font>', styles['cover_sub'])],
         [Paragraph(f'<b>{feedback.profile_label}</b>', styles['cover_kicker'])],
         [Spacer(1, 60)],
         [Paragraph(f'Documento confidencial • {brand.name}', styles['cover_meta'])],
        ],
        colWidths=[A4[0] - 3 * cm],
    )
    cover_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), primary_dark),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 20),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 20),
        ('LEFTPADDING', (0, 0), (-1, -1), 30),
        ('RIGHTPADDING', (0, 0), (-1, -1), 30),
    ]))

    story.append(Spacer(1, 1.5*cm))
    story.append(cover_table)
    story.append(PageBreak())

    # =========================
    # PÁGINA 2 — RESUMO EXECUTIVO
    # =========================
    story.append(Paragraph('Resumo Executivo', styles['h1']))
    story.append(Paragraph(
        f'Este relatório apresenta a consolidação completa da avaliação 180° de '
        f'<b>{assignment.employee.name}</b>, considerando a autoavaliação do colaborador e a '
        f'percepção do gestor direto. O ciclo avalia <b>{len(summary["rows"])} critérios</b> '
        f'distribuídos em <b>{len(summary["category_compare"])} competências</b>, resultando em uma '
        f'nota final consolidada de <b>{summary["final_avg"]:.2f}</b> '
        f'(perfil <b>{feedback.profile_label}</b>).',
        styles['body'],
    ))
    story.append(Spacer(1, 12))

    # KPIs em destaque
    kpi_data = [[
        Paragraph('AUTOAVALIAÇÃO', styles['metric_lbl']),
        Paragraph('AVALIAÇÃO GESTOR', styles['metric_lbl']),
        Paragraph('MÉDIA FINAL', styles['metric_lbl']),
    ], [
        Paragraph(f'{summary["employee_avg"]:.2f}', styles['metric_val']),
        Paragraph(f'{summary["manager_avg"]:.2f}', styles['metric_val']),
        Paragraph(f'{summary["final_avg"]:.2f}', styles['metric_val']),
    ]]
    kpi_table = Table(kpi_data, colWidths=[6*cm, 6*cm, 6*cm], rowHeights=[0.9*cm, 1.4*cm])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#1e40af')),
        ('BACKGROUND', (1, 0), (1, -1), primary),
        ('BACKGROUND', (2, 0), (2, -1), primary_dark),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 14))

    # Perfil e tabela de pontos fortes x desenvolvimento
    story.append(Paragraph('Pontos Fortes e Oportunidades de Desenvolvimento', styles['h2']))
    strength_list = [c for c in summary['category_avg'] if c['score'] >= 4.0][:5]
    development_list = sorted([c for c in summary['category_avg'] if c['score'] < 4.0], key=lambda x: x['score'])[:5]
    if not strength_list:
        strength_list = sorted(summary['category_avg'], key=lambda x: x['score'], reverse=True)[:3]
    if not development_list:
        development_list = sorted(summary['category_avg'], key=lambda x: x['score'])[:3]

    max_rows = max(len(strength_list), len(development_list))
    sd_data = [[
        Paragraph('<b>✓ PONTOS FORTES</b>', styles['metric_lbl']),
        Paragraph('<b>↑ OPORTUNIDADES DE DESENVOLVIMENTO</b>', styles['metric_lbl']),
    ]]
    for i in range(max_rows):
        s = strength_list[i] if i < len(strength_list) else None
        d = development_list[i] if i < len(development_list) else None
        sd_data.append([
            Paragraph(f"<b>{s['category']}</b><br/><font color='#15803d'>Nota: {s['score']:.2f}</font>", styles['small']) if s else Paragraph('', styles['small']),
            Paragraph(f"<b>{d['category']}</b><br/><font color='#dc2626'>Nota: {d['score']:.2f}</font>", styles['small']) if d else Paragraph('', styles['small']),
        ])
    sd_table = Table(sd_data, colWidths=[(A4[0] - 3*cm)/2, (A4[0] - 3*cm)/2])
    sd_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#15803d')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#b45309')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(sd_table)
    story.append(PageBreak())

    # =========================
    # PÁGINA 3 — GRÁFICOS
    # =========================
    story.append(Paragraph('Análise Visual de Competências', styles['h1']))
    story.append(Paragraph(
        'Comparação visual entre a autoavaliação do colaborador e a percepção do gestor para cada competência avaliada.',
        styles['body'],
    ))
    story.append(Spacer(1, 10))

    bar_buf = generate_bar_chart(summary['category_compare'])
    if bar_buf:
        img = Image(bar_buf, width=16*cm, height=max(8, len(summary['category_compare']) * 1.1)*cm)
        img.hAlign = 'CENTER'
        story.append(img)
        story.append(Spacer(1, 12))

    radar_buf = generate_radar_chart(summary['category_compare'])
    if radar_buf:
        story.append(PageBreak())
        story.append(Paragraph('Mapa de Competências — Visão 180°', styles['h1']))
        story.append(Paragraph(
            'O gráfico radar permite identificar rapidamente o equilíbrio entre as competências, '
            'mostrando a sobreposição da autoavaliação (amarelo) com a percepção do gestor (azul).',
            styles['body'],
        ))
        story.append(Spacer(1, 10))
        img = Image(radar_buf, width=14*cm, height=14*cm)
        img.hAlign = 'CENTER'
        story.append(img)

    # =========================
    # PÁGINA 4 — DETALHAMENTO POR CRITÉRIO
    # =========================
    story.append(PageBreak())
    story.append(Paragraph('Detalhamento por Critério', styles['h1']))
    story.append(Paragraph(
        'Detalhamento individual de cada critério avaliado, com notas atribuídas pela autoavaliação, pelo gestor e a nota consolidada.',
        styles['body'],
    ))
    story.append(Spacer(1, 8))

    detail_data = [['Competência', 'Critério avaliado', 'Auto', 'Gestor', 'Final']]
    for item in summary['rows']:
        detail_data.append([
            Paragraph(f"<b>{item['question'].category}</b>", styles['small']),
            Paragraph(item['question'].text, styles['small']),
            str(item['employee'].score if item['employee'] else '-'),
            str(item['manager'].score if item['manager'] else '-'),
            f"{item['final_score']:.1f}" if item['final_score'] is not None else '-',
        ])
    detail_table = Table(detail_data, colWidths=[3.0*cm, 8.5*cm, 1.4*cm, 1.7*cm, 1.7*cm], repeatRows=1)
    detail_style = [
        ('BACKGROUND', (0, 0), (-1, 0), primary),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]
    for i, item in enumerate(summary['rows'], start=1):
        if i % 2 == 0:
            detail_style.append(('BACKGROUND', (0, i), (-1, i), light))
        if item['final_score'] is not None:
            color_hex = score_color_hex(item['final_score'])
            detail_style.append(('TEXTCOLOR', (4, i), (4, i), colors.HexColor(color_hex)))
            detail_style.append(('FONTNAME', (4, i), (4, i), 'Helvetica-Bold'))
    detail_table.setStyle(TableStyle(detail_style))
    story.append(detail_table)

    # =========================
    # PÁGINA 5 — HISTÓRICO
    # =========================
    if history_data:
        story.append(PageBreak())
        story.append(Paragraph('Histórico de Ciclos Anteriores', styles['h1']))
        story.append(Paragraph(
            'Evolução do desempenho do colaborador ao longo dos ciclos anteriores de avaliação 180°.',
            styles['body'],
        ))
        story.append(Spacer(1, 10))

        history_buf = generate_history_chart(history_data, summary['final_avg'])
        if history_buf:
            img = Image(history_buf, width=16*cm, height=8*cm)
            img.hAlign = 'CENTER'
            story.append(img)
            story.append(Spacer(1, 14))

        hist_data = [['Ciclo', 'Encerramento', 'Auto', 'Gestor', 'Final']]
        for h in history_data:
            hist_data.append([
                h['cycle'],
                h['date'].strftime('%d/%m/%Y'),
                f"{h['employee_avg']:.2f}",
                f"{h['manager_avg']:.2f}",
                f"{h['final_avg']:.2f}",
            ])
        hist_data.append([
            assignment.cycle.name + ' (atual)',
            assignment.cycle.end_date.strftime('%d/%m/%Y'),
            f"{summary['employee_avg']:.2f}",
            f"{summary['manager_avg']:.2f}",
            f"{summary['final_avg']:.2f}",
        ])
        hist_table = Table(hist_data, colWidths=[6*cm, 3*cm, 2.3*cm, 2.3*cm, 2.3*cm], repeatRows=1)
        hist_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), primary),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), secondary),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#cbd5e1')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(hist_table)

    # =========================
    # PÁGINA 6 — FEEDBACK CONSOLIDADO
    # =========================
    story.append(PageBreak())
    story.append(Paragraph('Feedback Consolidado', styles['h1']))
    for block in (feedback.editable_feedback or '').split('\n\n'):
        if block.strip():
            story.append(Paragraph(block.replace('\n', '<br/>'), styles['body']))
            story.append(Spacer(1, 8))

    if feedback.manager_comments:
        story.append(Spacer(1, 6))
        story.append(Paragraph('Comentários do Gestor', styles['h2']))
        story.append(Paragraph(feedback.manager_comments.replace('\n', '<br/>'), styles['body']))

    # =========================
    # PÁGINA 7 — PDI VISUAL 30/60/90
    # =========================
    story.append(PageBreak())
    story.append(Paragraph('Plano de Desenvolvimento Individual (PDI)', styles['h1']))
    story.append(Paragraph(
        'Plano estruturado de desenvolvimento com objetivos, ações, indicadores e prazos 30 / 60 / 90 dias.',
        styles['body'],
    ))
    story.append(Spacer(1, 10))

    # Timeline visual 30-60-90
    timeline_data = [[
        Paragraph('<b>30 DIAS</b><br/><font size="9">Aprendizado e prática inicial</font>', styles['metric_lbl']),
        Paragraph('<b>60 DIAS</b><br/><font size="9">Aplicação e consistência</font>', styles['metric_lbl']),
        Paragraph('<b>90 DIAS</b><br/><font size="9">Avaliação e consolidação</font>', styles['metric_lbl']),
    ]]
    timeline_table = Table(timeline_data, colWidths=[6*cm, 6*cm, 6*cm], rowHeights=[1.4*cm])
    timeline_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#16a34a')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#ca8a04')),
        ('BACKGROUND', (2, 0), (2, 0), primary),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(timeline_table)
    story.append(Spacer(1, 14))

    for block in (feedback.editable_pdi or '').split('\n\n'):
        if block.strip():
            story.append(Paragraph(block.replace('\n', '<br/>'), styles['body_left']))
            story.append(Spacer(1, 8))

    # =========================
    # PÁGINA FINAL — ASSINATURAS
    # =========================
    story.append(PageBreak())
    story.append(Paragraph('Validação do Plano', styles['h1']))
    story.append(Paragraph(
        'Documento ciente e validado pelas partes envolvidas. As assinaturas formalizam o '
        'compromisso com o plano de desenvolvimento descrito.',
        styles['body'],
    ))
    story.append(Spacer(1, 40))

    signature_line = '_' * 50
    sig_data = [
        [Paragraph(signature_line, styles['body']), Paragraph(signature_line, styles['body'])],
        [Paragraph(f'<b>{assignment.employee.name}</b><br/>Colaborador<br/><font size="8" color="#64748b">{assignment.employee.position}</font>', styles['body']),
         Paragraph(f'<b>{assignment.manager.name}</b><br/>Gestor responsável<br/><font size="8" color="#64748b">{assignment.manager.position}</font>', styles['body'])],
        [Spacer(1, 30), Spacer(1, 30)],
        [Paragraph('Data: ___/___/______', styles['small']), Paragraph('Data: ___/___/______', styles['small'])],
    ]
    sig_table = Table(sig_data, colWidths=[(A4[0] - 3*cm)/2, (A4[0] - 3*cm)/2])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 50))
    story.append(Paragraph(
        f'<i>Documento gerado eletronicamente pelo sistema de RH 180° em {datetime.utcnow().strftime("%d/%m/%Y às %H:%M")}.</i>',
        styles['small'],
    ))
    story.append(Paragraph(
        f'<i>{brand.name} • Confidencial • Uso interno exclusivo da liderança de RH.</i>',
        styles['small'],
    ))

    doc.build(story, onFirstPage=lambda c, d: None, onLaterPages=page_decorator)
    buffer.seek(0)
    log_action('Gerou PDF do relatório', 'assignment', assignment.id, assignment.employee.name)
    filename = f"relatorio_180_{assignment.employee.name.lower().replace(' ', '_')}_{assignment.cycle.start_date.strftime('%Y%m')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')


# =========================================================
# SEED
# =========================================================
def seed_database():
    db.create_all()
    if CompanyBrand.query.first():
        return

    brand = CompanyBrand()
    db.session.add(brand)

    manager = User(
        name='Administrador Posto do Boi',
        email='gestor@postodoboi.com',
        role='manager',
        department='Administração',
        position='Gestor Geral',
        unit='Matriz',
        active=True,
        admission_date=date(2020, 1, 5),
    )
    manager.set_password('123456')
    db.session.add(manager)
    db.session.flush()

    employees_seed = [
        ('Ana Lima', 'ana@postodoboi.com', 'Atendimento', 'Caixa', 'Posto do Boi'),
        ('Bruno Souza', 'bruno@expressdoboi.com', 'Operação', 'Frentista', 'Posto do Boi'),
        ('Camila Rocha', 'camila@expressdoboi.com', 'Conveniência', 'Atendente', 'Express do Boi'),
        ('Diego Pereira', 'diego@expressdoboi.com', 'Conveniência', 'Repositor', 'Express do Boi'),
    ]
    for name, email, dept, pos, unit in employees_seed:
        emp = User(
            name=name, email=email, role='employee',
            department=dept, position=pos, unit=unit,
            manager_id=manager.id, active=True,
            admission_date=date(2023, 1, 10),
        )
        emp.set_password('123456')
        db.session.add(emp)

    questions_seed = [
        ('Atendimento ao Cliente', 'Atende clientes com cordialidade, agilidade e atenção, oferecendo uma experiência de boas-vindas em todas as interações.', 'Cumprimentar, ouvir, resolver e despedir-se com atenção.'),
        ('Atendimento ao Cliente', 'Sabe ouvir reclamações com paciência e busca a melhor solução, mantendo a calma e o respeito mesmo em situações difíceis.', 'Escuta ativa, foco em solução, postura profissional.'),
        ('Operação e Segurança', 'Segue rigorosamente os procedimentos de segurança no manuseio de combustíveis, equipamentos e produtos.', 'EPIs, sinalização, prevenção de acidentes.'),
        ('Operação e Segurança', 'Mantém o posto de trabalho limpo, organizado e abastecido conforme o padrão da unidade.', 'Limpeza, reposição, organização visual.'),
        ('Disciplina e Pontualidade', 'É pontual, cumpre escala de trabalho e comunica eventuais ausências com antecedência.', 'Pontualidade, comprometimento, comunicação.'),
        ('Disciplina e Pontualidade', 'Cumpre as regras da empresa, uniforme, conduta e processos definidos pela liderança.', 'Aderência ao padrão da empresa.'),
        ('Trabalho em Equipe', 'Colabora com colegas das diferentes funções (caixa, frentista, conveniência) para garantir o bom funcionamento do turno.', 'Cooperação, suporte mútuo, foco no time.'),
        ('Trabalho em Equipe', 'Compartilha informações relevantes do turno (estoque, ocorrências, clientes) com a liderança e colegas.', 'Comunicação clara, repasse de turno.'),
        ('Vendas e Conveniência', 'Conhece os produtos da loja e sugere ativamente itens adicionais e promoções para os clientes.', 'Postura comercial, conhecimento do mix.'),
        ('Vendas e Conveniência', 'Confere e cuida do estoque, validade e organização dos produtos sob sua responsabilidade.', 'Reposição, validade, organização.'),
        ('Responsabilidade Financeira', 'Realiza operações no caixa (dinheiro, cartão, pix) com precisão e segurança, evitando erros e divergências.', 'Conferência de caixa, atenção a fraudes.'),
        ('Atitude e Aprendizado', 'Demonstra disposição para aprender, aceita feedback e busca melhorar continuamente seu desempenho.', 'Receptividade ao feedback, autodesenvolvimento.'),
    ]
    for category, text, expected in questions_seed:
        db.session.add(Question(category=category, text=text, expected_behavior=expected, active=True))

    cycle = EvaluationCycle(
        name='Ciclo 2026.1 - Posto do Boi / Express do Boi',
        start_date=date(2026, 5, 1),
        end_date=date(2026, 6, 30),
        status='active',
    )
    db.session.add(cycle)
    db.session.flush()

    for emp in User.query.filter_by(role='employee').all():
        db.session.add(Assignment(cycle_id=cycle.id, employee_id=emp.id, manager_id=manager.id))

    db.session.commit()


with app.app_context():
    seed_database()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
