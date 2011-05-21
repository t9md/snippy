#!/usr/bin/env python
# -*- coding: utf-8 -*-
from flask import Flask, session, redirect, url_for, escape, request, abort, flash
from flask import render_template, Response

import datetime, os, sys, sha
from functools import wraps
from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Boolean
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, mapper, relation, sessionmaker, scoped_session
from sqlalchemy.sql import exists

from pygments import highlight
from pygments.lexers import PythonLexer, PerlLexer, RubyLexer, JavaLexer
from pygments.formatters import HtmlFormatter

from sample_code import sample_code

app = Flask(__name__)
app.debug = False
app.secret_key = os.urandom(24)

if not app.debug:
    import logging
    import logging.handlers
    dirname_ = os.path.dirname(os.path.abspath(__file__))
    LOG_FILENAME = os.path.join(dirname_ , __name__ + ".log")
    file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILENAME, maxBytes=20, backupCount=5)
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

#---------------------------------
#### Variable
# 定数
RUBY   = 'Ruby'
PERL   = 'Perl'
PYTHON = 'Python'
JAVA   = 'Java'

# app.config.from_object(__name__)

Base = declarative_base()
DB = 'snippy.db'
engine = create_engine("sqlite:///%s" % DB)
#engine.echo=True
Session = scoped_session(sessionmaker(bind=engine))
#---------------------------------
#### Utility function
def Query(obj)  : return Session().query(obj)
def Commit()    : Session().commit()
def Add(obj)    : Session().add(obj); return obj
def AddAll(obj) : Session().add_all(obj)

## ApplicationController
PUBLIC_URL = 'http://localhost:5000'
SUPPORTED_LANG = [ 'Ruby', 'Python', 'Perl', 'Java' ]
ENTRY_PER_PAGE = 5

def login_require(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('username') is not None:
            return f(*args, **kwargs)
        else:
            return redirect(url_for('login'))
    return decorated_function

@app.route('/test/')
@app.route('/test/<name>')
def test(name=None):
    return render_template("test.html", name=name)

@app.route('/')
@app.route('/<int:sni_id>')
def index(sni_id=None):
    query = {}
    page  = int(request.values.get('page', 1))

    if sni_id:
        snip = [Snippet.get_one(id=sni_id)]
        total = 1
    else:
        author = request.values.get('author')
        lang   = request.values.get('lang')
        if  author: query = {"author": author }
        elif lang: query = {"lang": lang }

        skip = (page-1)*ENTRY_PER_PAGE
        snippets = Snippet.get(**query)
        total    = snippets.count()
        snip = snippets.order_by(Snippet.id.desc()).offset(skip).limit(ENTRY_PER_PAGE)

    newer, older = _prepare_paging(snip, page, total, **query)
    users = Query(User).all()
    current_user = session.get('username',False)
    languages = [ (lang, Snippet.get(lang=lang).count()) for lang in SUPPORTED_LANG ]
    return render_template("index.html",snippets=snip, users = users, 
            languages = languages, newer=newer, older=older, current_user=current_user)
    
def _prepare_paging(lis, page=1, total=1, **query):
    def _build_qs(page, **query):
        if not page: return False
        query['page'] = str(page)
        return "?" + "&".join([ "=".join([k,v]) for (k,v) in query.items() ])

    page_newest = 1
    page_oldest = (total/ENTRY_PER_PAGE) + 1

    def _page_guide(page):
        """return (newer, older)"""
        newer = False if page == page_newest else page - 1
        older = False if page == page_oldest else page + 1
        return (newer, older)

    newer, older = map(lambda x: _build_qs(x, **query), _page_guide(page))
    return (newer, older)


@app.route('/add')
@login_require
def add():
    return render_template("edit.html", optlist=SUPPORTED_LANG)

@app.route('/edit/<int:sni_id>')
@login_require
def edit(sni_id):
    return render_template("edit.html", sni=Snippet.get_one(id=sni_id), optlist=SUPPORTED_LANG)

@app.route('/delete/<int:sni_id>')
@login_require
def delete(sni_id):
    Snippet.delete(id=sni_id)
    return redirect(url_for('index'))

@app.route('/create_or_update', methods=['POST'])
@login_require
def create_or_update():
    user =  session.get('username', False)
    sni_id = request.form.get('sni_id') # avoid KeyError
    title  = request.form['title']
    code   = request.form['code']
    lang   = request.form['lang']
    if sni_id:
        snip = Snippet.get_one(id=sni_id)
        snip.title = title
        snip.code  = code
        snip.lang  = lang
        Commit()
        app.logger.info("%s is updated by %s" % (snip.id, user))
    else:
        snip = Snippet.create(user, title, code, lang)
        app.logger.info("%s is created by %s" % (snip.id, user))
    return redirect("/" + str(snip.id))

# def login_p():
    # return session.get('username', False)

@app.route('/raw/<int:sni_id>')
def raw(sni_id):
    return Response(Snippet.get_one(id=sni_id).code, mimetype='text/plain')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = False
    if request.method == 'POST':
        if authenticate(request.form['username'], request.form['password']):
            session['username'] = request.form['username']
            flash('Your were successfully logged in')
            return redirect(url_for('index'))
        else:
            error = 'Invalid credentials'
    return render_template("login.html", error=error)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

def authenticate(username, password):
    User.get_all()
    user = User.get_one(name=username)
    if user and user.password == sha.new(password).hexdigest():
        return True

#---------------------------------
class ORMapperUtils(object):
    @classmethod
    def create(cls, *args, **kwargs):
        obj = Add(cls(*args, **kwargs))
        Commit()
        return obj

    @classmethod
    def count(cls):
        return Query(Snippet).count()

    @classmethod
    def get(cls, *args, **kwargs):
        return Query(cls).filter_by(**kwargs)

    @classmethod
    def get_one(cls, *args, **kwargs):
        try:
            return cls.get(**kwargs).one()
        except:
            return None

    @classmethod
    def get_all(cls, *args, **kwargs):
        return cls.get(**kwargs).all()

    @classmethod
    def delete(cls, *args, **kwargs):
        cls.get(*args,**kwargs).delete()
        Commit()

#### ORMapped Object( by SQLAlchemy )
# ORMapping するため、Base を継承する。※Base = declarative_base()
class Snippet(Base, ORMapperUtils):
    __tablename__ = "snippets"
 
    id     = Column(Integer, primary_key = True)
    date   = Column(DateTime)
    author = Column(String)
    title  = Column(String)
    code   = Column(String)
    lang   = Column(String)
 
    lexer = {
        'Ruby'   : RubyLexer,
        'Python' : PythonLexer,
        'Perl'   : PerlLexer,
        'Java'   : JavaLexer,
    }

    def __init__(self, author="", title="", code="", lang=""):
        """Constructor"""
        self.date   = datetime.datetime.now()
        self.author = author
        self.title  = title
        self.code   = code
        self.lang   = lang
 
    def __repr__(self):
        return "<Snippet('%s','%s', '%s')>" % (self.date, self.title, self.author)

    def highlight(self):
        formatter = HtmlFormatter()
        formatter.outencoding = 'utf-8'
        return highlight(self.code, self.lexer[self.lang](), formatter)
 
#---------------------------------
class User(Base, ORMapperUtils):
    __tablename__ = "users"

    id       = Column(Integer, primary_key = True)
    name     = Column(String, nullable = False)
    password = Column(String)
    admin    = Column(Boolean)

    @classmethod
    def create(cls, *args, **kwargs):
        Add(cls(*args, **kwargs))
        Commit()

    def __init__(self, name, password, admin=False):
        self.name = name
        # sha1 で保存
        self.password = sha.new(password).hexdigest()
        self.admin = admin
 
    def __repr__(self):
        return "<User('%s', admin=%d)>" % (self.name, self.admin)
 
#---
#### スキーマの初期化と、サンプルデータの投入
def init():
    if os.path.isfile(DB): os.remove(DB)
    metadata = Base.metadata
    metadata.create_all(engine)
    # s = Session()
    AddAll([
        User('t9md'    , 't9mdpass'    , True),
        User('fkei'    , 'fkeipass'     ),
        User('namikawa', 'namikawapass' ),
        User('kuwano'  , 'kuwanopass'   ),
        User('sakamoto', 'sakamotopass' ),
        User('oinume'  , 'oinumepass'   ),
        User('wyusaku'  , 'yusakupass' ),
        Snippet('t9md'    , 'I love Ruby'  , sample_code[RUBY]  , RUBY)  ,
        Snippet('sakamoto', 'I love Python', sample_code[PYTHON], PYTHON),
        Snippet('fkei'    , 'I love Python', sample_code[PYTHON], PYTHON),
        Snippet('sakamoto', 'I love Ruby'  , sample_code[PYTHON], PYTHON),
        Snippet('sakamoto', 'I love Ruby'  , sample_code[PYTHON], PYTHON),
        Snippet('t9md'    , 'I love Ruby'  , sample_code[RUBY]  , RUBY)  ,
        Snippet('t9md'    , 'I love Ruby'  , sample_code[RUBY]  , RUBY)  ,
        Snippet('t9md'    , 'I love Ruby'  , sample_code[RUBY]  , RUBY)  ,
        ])
    Commit()

#---------------------------------
static_files = {
    '/static': os.path.join(os.path.dirname(__file__), 'static'),
}

#### Main
if __name__ == '__main__':
    if len(sys.argv) == 2:
        cmd = sys.argv[1]
        if cmd == 'init':
            init()
            print 'init'
    else:
        app.run(static_files=static_files)
