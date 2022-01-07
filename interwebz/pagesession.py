from flask import session
from uuid import uuid4

class PageSession(object):
  def __init__(self, handshake=True):
    if handshake or 'session_id' not in session:
      self.relogin()
    else:
      self.id = session['session_id']


  def relogin(self):
      self.id = str(uuid4())
      session['session_id'] = self.id


  def __str__(self):
    return str(self.id)
