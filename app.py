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
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak,
)

# =========================================================
# APP / DATABASE
# =========================================================

app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')

os.makedirs(INSTANCE_DIR, exist_ok=True)

DB_PATH = os.path.join(INSTANCE_DIR, 'postodoboi_rh.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DB_PATH}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'postodoboi-rh-secret'

db = SQLAlchemy(app)

# =========================================================
# SAFE COMMIT
# =========================================================

def safe_commit():
    try:
        db.session.commit()
        return True, None

    except Exception as e:
        db.session.rollback()
        return False, str(e)

# =========================================================
# CORES
# =========================================================

IPIRANGA_BLUE = '#003B7A'
IPIRANGA_BLUE_DARK = '#001f44'
IPIRANGA_YELLOW = '#FFCC00'
IPIRANGA_YELLOW_DARK = '#e6b800'

# =========================================================
# MODELOS
# =========================================================

class CompanyBrand(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(120),
        nullable=False,
        default='Posto do Boi e Express do Boi'
    )

    mission = db.Column(
        db.Text,
        nullable=False,
        default='Combustível, conveniência e atendimento de excelência.'
    )

    values = db.Column(
        db.Text,
        nullable=False,
        default='Atendimento\nSegurança\nDisciplina\nEquipe\nResponsabilidade'
    )

    primary_color = db.Column(
        db.String(20),
        nullable=False,
        default='#003B7A'
    )

    secondary_color = db.Column(
        db.String(20),
        nullable=False,
        default='#FFCC00'
    )


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False)

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False
    )

    department = db.Column(
        db.String(120),
        nullable=False
    )

    position = db.Column(
        db.String(120),
        nullable=False
    )

    unit = db.Column(
        db.String(120),
        nullable=False,
        default='Posto do Boi'
    )

    admission_date = db.Column(
        db.Date,
        nullable=True
    )

    active = db.Column(
        db.Boolean,
        default=True
    )

    manager_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id')
    )

    manager = db.relationship(
        'User',
        remote_side=[id],
        backref='team_members'
    )

    def set_password(self, raw: str):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str):
        return check_password_hash(self.password_hash, raw)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    category = db.Column(
        db.String(120),
        nullable=False
    )

    text = db.Column(
        db.Text,
        nullable=False
    )

    expected_behavior = db.Column(
        db.Text,
        nullable=True
    )

    active = db.Column(
        db.Boolean,
        default=True
    )


class EvaluationCycle(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(120),
        nullable=False
    )

    start_date = db.Column(
        db.Date,
        nullable=False
    )

    end_date = db.Column(
        db.Date,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default='draft'
    )


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    cycle_id = db.Column(
        db.Integer,
        db.ForeignKey('evaluation_cycle.id'),
        nullable=False
    )

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=False
    )

    manager_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),
        nullable=False
    )

    cycle = db.relationship(
        'EvaluationCycle',
        backref='assignments'
    )

    employee = db.relationship(
        'User',
        foreign_keys=[employee_id],
        backref='employee_assignments'
    )

    manager = db.relationship(
        'User',
        foreign_keys=[manager_id],
        backref='manager_assignments'
    )


class Response(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    assignment_id = db.Column(
        db.Integer,
        db.ForeignKey('assignment.id'),
        nullable=False
    )

    question_id = db.Column(
        db.Integer,
        db.ForeignKey('question.id'),
        nullable=False
    )

    evaluator_role = db.Column(
        db.String(20),
        nullable=False
    )

    score = db.Column(
        db.Integer,
        nullable=False
    )

    comment = db.Column(
        db.Text,
        nullable=False
    )

    submitted_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    assignment = db.relationship(
        'Assignment',
        backref='responses'
    )

    question = db.relationship('Question')


# =========================================================
# LOGIN
# =========================================================

@app.before_request
def load_globals():
    user_id = session.get('user_id')

    if user_id:
        g.current_user = User.query.get(user_id)
    else:
        g.current_user = None


def login_required(role=None):
    def decorator(fn):

        @wraps(fn)
        def wrapper(*args, **kwargs):

            if not g.current_user:
                return redirect(url_for('login'))

            if role and g.current_user.role != role:
                flash('Sem permissão.', 'danger')
                return redirect(url_for('login'))

            return fn(*args, **kwargs)

        return wrapper

    return decorator

# =========================================================
# LOG
# =========================================================

def log_action(action, entity_type, entity_id=None):

    try:
        pass
    except:
        pass

# =========================================================
# ROTAS
# =========================================================

@app.route('/', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form.get('email', '').strip().lower()

        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()

        if user and user.active and user.check_password(password):

            session['user_id'] = user.id

            flash('Login realizado.', 'success')

            if user.role == 'manager':
                return redirect(url_for('manager_dashboard'))

            return redirect(url_for('employee_dashboard'))

        flash('Credenciais inválidas.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():

    session.clear()

    flash('Logout realizado.', 'info')

    return redirect(url_for('login'))


@app.route('/manager/dashboard')
@login_required(role='manager')
def manager_dashboard():

    assignments = Assignment.query.filter_by(
        manager_id=g.current_user.id
    ).all()

    return render_template(
        'manager_dashboard.html',
        assignments=assignments
    )


@app.route('/employee/dashboard')
@login_required(role='employee')
def employee_dashboard():

    assignments = Assignment.query.filter_by(
        employee_id=g.current_user.id
    ).all()

    return render_template(
        'employee_dashboard.html',
        assignments=assignments
    )

# =========================================================
# EMPLOYEES
# =========================================================

@app.route('/employees', methods=['GET', 'POST'])
@login_required(role='manager')
def employees():

    managers = User.query.filter_by(
        role='manager'
    ).all()

    if request.method == 'POST':

        admission_str = request.form.get(
            'admission_date',
            ''
        ).strip()

        user = User(
            name=request.form['name'].strip(),
            email=request.form['email'].strip().lower(),
            role='employee',
            department=request.form['department'].strip(),
            position=request.form['position'].strip(),
            unit=request.form.get('unit', 'Posto do Boi').strip(),
            manager_id=int(request.form['manager_id']),
            active=True,
            admission_date=datetime.strptime(
                admission_str,
                '%Y-%m-%d'
            ).date() if admission_str else None
        )

        user.set_password(
            request.form.get('password') or '123456'
        )

        db.session.add(user)

        ok, err = safe_commit()

        if not ok:
            flash(f'Erro ao salvar: {err}', 'danger')
            return redirect(url_for('employees'))

        flash('Colaborador cadastrado.', 'success')

        return redirect(url_for('employees'))

    employees_list = User.query.filter_by(
        role='employee'
    ).all()

    return render_template(
        'employees.html',
        employees=employees_list,
        managers=managers
    )

# =========================================================
# QUESTIONS
# =========================================================

@app.route('/questions', methods=['GET', 'POST'])
@login_required(role='manager')
def questions():

    if request.method == 'POST':

        question = Question(
            category=request.form['category'].strip(),
            text=request.form['text'].strip(),
            expected_behavior=request.form.get(
                'expected_behavior',
                ''
            ).strip(),
            active=True
        )

        db.session.add(question)

        ok, err = safe_commit()

        if not ok:
            flash(f'Erro ao salvar: {err}', 'danger')
            return redirect(url_for('questions'))

        flash('Pergunta cadastrada.', 'success')

        return redirect(url_for('questions'))

    questions_list = Question.query.all()

    return render_template(
        'questions.html',
        questions=questions_list
    )

# =========================================================
# INIT DATABASE
# =========================================================

def seed_database():

    db.create_all()

    if User.query.filter_by(
        email='gestor@postodoboi.com'
    ).first():
        return

    manager = User(
        name='Administrador',
        email='gestor@postodoboi.com',
        role='manager',
        department='Administração',
        position='Gestor Geral',
        unit='Matriz',
        active=True,
        admission_date=date.today()
    )

    manager.set_password('123456')

    db.session.add(manager)

    safe_commit()

# =========================================================
# START
# =========================================================

with app.app_context():
    seed_database()

if __name__ == '__main__':
    app.run(
        debug=True,
        host='0.0.0.0',
        port=5000
    )
