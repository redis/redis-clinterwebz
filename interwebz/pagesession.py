from flask import request, session
from uuid import uuid4


class PageSession(object):
    def __init__(self):
        cid = request.json.get('id', None)
        sid = session.get('id', None)
        if cid is None or sid is None or cid != sid:
            self.relogin()

    def relogin(self):
        session['id'] = str(uuid4())

    def __str__(self):
        return str(session['id'])
