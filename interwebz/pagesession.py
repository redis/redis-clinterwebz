from flask import request, session
from uuid import uuid4


class PageSession(object):
    def __init__(self):
        cid = request.json.get('id')
        if cid is None:
            self.relogin()
        else:
            session['id'] = cid

    def relogin(self):
        session['id'] = str(uuid4())

    def __str__(self):
        return str(session['id'])
