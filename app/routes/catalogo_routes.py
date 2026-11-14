from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from ..services import catalogo_service as service

catalogos = Blueprint('catalogos', __name__)


@catalogos.route('/inventario/catalogos', methods=['GET', 'POST'])
def index():
    kind = request.args.get('kind', 'reference')
    if kind not in service.KINDS:
        abort(404)
    edit = service.get_item(request.args.get('edit'), kind)
    data = edit.to_dict() if edit else {}
    error = None
    suggestions = []
    exact_duplicate = False
    if request.method == 'POST':
        data = request.form.to_dict()
        try:
            service.save_item(kind, data)
            flash('Catálogo actualizado.')
            return redirect(url_for('catalogos.index', kind=kind))
        except service.SimilarReferenceError as exc:
            suggestions = exc.suggestions
            exact_duplicate = exc.exact
        except ValueError as exc:
            error = str(exc)
    return render_template('catalogos/index.html', kinds=service.KINDS, kind=kind,
                           rows=service.list_items(kind), references=service.list_items('reference'),
                           brands=service.list_items('brand'), data=data, error=error,
                           suggestions=suggestions, exact_duplicate=exact_duplicate,
                           capacities=service.CAPACITY_OPTIONS, active='inventario')
