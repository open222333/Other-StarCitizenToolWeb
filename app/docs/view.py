from flask import Blueprint, render_template
from src import ADMIN_TITLE

app_docs = Blueprint('app_docs', __name__)


@app_docs.route('/')
def index():
    return render_template('docs/index.html', admin_title=ADMIN_TITLE)
