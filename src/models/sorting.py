"""列表排序參數（全站共用）：前端點表頭送 sort_by／sort_dir，這裡依白名單換成 MongoDB 的 sort。

    spec = sort_spec(sort_by, sort_dir, {'name': 'name_lower', 'type': 'type'},
                     default=[('name_lower', 1)])
    col.find(filt).sort(spec)

白名單外的 sort_by 一律用 default（不讓前端排任意欄位）；排序欄位相同時接 default 剩下的欄位、
最後接 _id，翻頁才不會因為同值的順序不固定而重複或漏掉。
"""


def sort_spec(sort_by, sort_dir, fields: dict, default: list) -> list:
    path = fields.get((sort_by or '').strip()) if sort_by else None
    if not path:
        spec = list(default)
    else:
        direction = -1 if (sort_dir or '').lower() == 'desc' else 1
        paths = list(path) if isinstance(path, (list, tuple)) else [path]
        spec = [(p, direction) for p in paths] + [x for x in default if x[0] not in paths]
    if not any(k == '_id' for k, _ in spec):
        spec.append(('_id', 1))
    return spec


def sort_args(args) -> tuple:
    """從 request.args 取 (sort_by, sort_dir)。"""
    return (args.get('sort_by') or '').strip(), (args.get('sort_dir') or 'asc').strip().lower()
