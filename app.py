from __future__ import annotations

from datetime import datetime, date
from functools import wraps
from io import BytesIO
from statistics import mean

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///postodoboi_rh.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'postodoboi-rh-secret'

db = SQLAlchemy(app)


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
    role = db.Column(db.String(20), nullable=False)  # 'manager' ou 'employee'
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
    status = db.Column(db.String(20), nullable=False, default='draft')  # draft, active, closed


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
    evaluator_role = db.Column(db.String(20), nullable=False)  # employee | manager
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
    for r in rows:
        if r['final_score'] is not None:
            by_category.setdefault(r['question'].category, []).append(r['final_score'])
    category_avg = [{'category': c, 'score': round(mean(v), 2)} for c, v in by_category.items()]
    category_avg.sort(key=lambda x: x['score'], reverse=True)
    return {
        'rows': rows,
        'employee_avg': round(mean(emp_scores), 2) if emp_scores else 0,
        'manager_avg': round(mean(mgr_scores), 2) if mgr_scores else 0,
        'final_avg': round(mean(final_scores), 2) if final_scores else 0,
        'category_avg': category_avg,
    }


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


# ---------- Painel Gestor ----------
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
    return render_template(
        'manager_dashboard.html',
        active_cycle=active_cycle,
        assignments=team,
        progress_data=progress_data,
        metrics=metrics,
    )


@app.route('/employee/dashboard')
@login_required(role='employee')
def employee_dashboard():
    assignments = Assignment.query.filter_by(employee_id=g.current_user.id).all()
    active_assignment = next((a for a in assignments if a.cycle.status == 'active'), None)
    active_questions = Question.query.filter_by(active=True).count()
    progress = assignment_progress(active_assignment) if active_assignment else {'percent': 0, 'employee_done': False, 'manager_done': False}
    return render_template(
        'employee_dashboard.html',
        assignments=assignments,
        active_assignment=active_assignment,
        active_questions=active_questions,
        progress=progress,
    )


# ---------- Empresa ----------
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
        db.session.commit()
        log_action('Atualizou dados da empresa', 'company', brand.id, brand.name)
        flash('Identidade da empresa atualizada.', 'success')
        return redirect(url_for('company_settings'))
    return render_template('company_settings.html', brand=brand)


# ---------- Colaboradores ----------
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
        db.session.commit()
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


# ---------- Perguntas ----------
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
        db.session.commit()
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


# ---------- Ciclos ----------
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


# ---------- Avaliações ----------
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
                    assignment_id=assignment.id,
                    question_id=q.id,
                    evaluator_role='employee',
                    score=score,
                    comment=comment,
                ))
        db.session.commit()
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
                    assignment_id=assignment.id,
                    question_id=q.id,
                    evaluator_role='manager',
                    score=score,
                    comment=comment,
                ))
        db.session.commit()
        regenerate_feedback(assignment)
        log_action('Concluiu avaliação do gestor', 'assignment', assignment.id, assignment.employee.name)
        flash('Avaliação do gestor registrada e feedback automático gerado.', 'success')
        return redirect(url_for('feedback_view', assignment_id=assignment.id))
    existing = {r.question_id: r for r in Response.query.filter_by(assignment_id=assignment.id, evaluator_role='manager').all()}
    return render_template('evaluation_form.html', assignment=assignment, questions=questions_list, existing=existing, mode='manager')


# ---------- Feedback / PDI ----------
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
        # força regeneração: limpa editáveis para puxar do automático
        feedback.editable_feedback = ''
        feedback.editable_pdi = ''
        db.session.commit()
    regenerate_feedback(assignment)
    log_action('Regenerou feedback/PDI', 'feedback', assignment.id, assignment.employee.name)
    flash('Feedback e PDI regenerados a partir das notas atuais.', 'info')
    return redirect(url_for('feedback_view', assignment_id=assignment.id))


# ---------- Histórico ----------
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


# ---------- PDF ----------
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

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=1.6 * cm, leftMargin=1.6 * cm,
        topMargin=1.4 * cm, bottomMargin=1.4 * cm,
    )
    base_styles = getSampleStyleSheet()
    styles = {
        'title': ParagraphStyle(name='Title2', parent=base_styles['Title'], fontSize=20, textColor=colors.HexColor(brand.primary_color)),
        'h2': ParagraphStyle(name='H2', parent=base_styles['Heading2'], fontSize=14, textColor=colors.HexColor('#222')),
        'h3': ParagraphStyle(name='H3', parent=base_styles['Heading3'], fontSize=12, textColor=colors.HexColor(brand.primary_color), spaceAfter=6),
        'body': ParagraphStyle(name='Body2', parent=base_styles['BodyText'], fontSize=10, leading=14),
        'small': ParagraphStyle(name='Small', parent=base_styles['BodyText'], fontSize=9, leading=12, textColor=colors.HexColor('#555')),
    }

    story = []
    story.append(Paragraph(brand.name, styles['title']))
    story.append(Paragraph('Relatório de Avaliação de Desempenho 180°', styles['h2']))
    story.append(Paragraph(
        f"Colaborador: <b>{assignment.employee.name}</b> | Cargo: {assignment.employee.position} | "
        f"Área: {assignment.employee.department} | Unidade: {assignment.employee.unit}",
        styles['body'],
    ))
    story.append(Paragraph(
        f"Gestor responsável: <b>{assignment.manager.name}</b> | Ciclo: {assignment.cycle.name} "
        f"({assignment.cycle.start_date.strftime('%d/%m/%Y')} a {assignment.cycle.end_date.strftime('%d/%m/%Y')})",
        styles['body'],
    ))
    story.append(Spacer(1, 10))

    metrics_table = Table(
        [
            ['Autoavaliação', 'Avaliação do gestor', 'Média final'],
            [f"{summary['employee_avg']:.2f}", f"{summary['manager_avg']:.2f}", f"{summary['final_avg']:.2f}"],
        ],
        colWidths=[5.5 * cm, 5.5 * cm, 5.5 * cm],
    )
    metrics_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(brand.primary_color)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d6dee7')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(metrics_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph('Consolidação por competência', styles['h3']))
    rows = [['Categoria', 'Pergunta', 'Auto', 'Gestor', 'Final']]
    for item in summary['rows']:
        rows.append([
            item['question'].category,
            Paragraph(item['question'].text, styles['small']),
            str(item['employee'].score if item['employee'] else '-'),
            str(item['manager'].score if item['manager'] else '-'),
            f"{item['final_score']:.1f}" if item['final_score'] is not None else '-',
        ])
    details_table = Table(rows, colWidths=[3.0 * cm, 8.5 * cm, 1.4 * cm, 1.7 * cm, 1.7 * cm], repeatRows=1)
    details_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(brand.secondary_color)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#d6dee7')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph(f"Perfil consolidado: <b>{feedback.profile_label}</b>", styles['h3']))
    story.append(Paragraph(f"Pontos fortes: {feedback.strengths or '—'}", styles['body']))
    story.append(Paragraph(f"Pontos de desenvolvimento: {feedback.development_points or '—'}", styles['body']))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Feedback consolidado', styles['h3']))
    for block in (feedback.editable_feedback or '').split('\n\n'):
        if block.strip():
            story.append(Paragraph(block.replace('\n', '<br/>'), styles['body']))
            story.append(Spacer(1, 4))

    story.append(Spacer(1, 8))
    story.append(Paragraph('Plano de Desenvolvimento Individual (PDI)', styles['h3']))
    for block in (feedback.editable_pdi or '').split('\n\n'):
        if block.strip():
            story.append(Paragraph(block.replace('\n', '<br/>'), styles['body']))
            story.append(Spacer(1, 4))

    if feedback.manager_comments:
        story.append(Spacer(1, 8))
        story.append(Paragraph('Comentários finais do gestor', styles['h3']))
        story.append(Paragraph(feedback.manager_comments.replace('\n', '<br/>'), styles['body']))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"Relatório gerado em {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} • {brand.name}",
        styles['small'],
    ))

    doc.build(story)
    buffer.seek(0)
    log_action('Gerou PDF do relatório', 'assignment', assignment.id, assignment.employee.name)
    filename = f"relatorio_180_{assignment.employee.name.lower().replace(' ', '_')}.pdf"
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
            name=name,
            email=email,
            role='employee',
            department=dept,
            position=pos,
            unit=unit,
            manager_id=manager.id,
            active=True,
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
