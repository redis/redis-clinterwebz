from flask import request
from uuid import uuid4

class PageSession(object):
  def __init__(self):
    if 'id' not in request.json:
      self.relogin()
    else:
      self.id = request.json['id']


  def relogin(self):
      self.id = str(uuid4())


  def __str__(self):
    return str(self.id)
